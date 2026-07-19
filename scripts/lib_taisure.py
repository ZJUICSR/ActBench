"""
ClawEval TAISURE API Client.

OpenAI-compatible client for the TAISURE gateway (https://taisure.com/v1), which
fronts many providers behind one key — e.g. deepseek-v4-pro, claude-opus-4.8,
gpt-5.5, qwen3.7-max. Target models still go through OpenClaw, not this client.

Routing note: TAISURE exposes BARE model ids (`deepseek-v4-pro`, not
`deepseek/deepseek-v4-pro`). To avoid colliding with the DeepSeek-direct and
OpenRouter routes, callers select this backend with an explicit `taisure/`
prefix (e.g. `taisure/claude-opus-4.8`), which is stripped before the request.
"""

from __future__ import annotations

import http.client
import json
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

from urllib import error, request

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "deepseek-v4-pro"
DEFAULT_MAX_TOKENS = 4096
DEFAULT_TEMPERATURE = 0.7
API_BASE = "https://taisure.com/v1"
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2.0  # seconds; delays: 2, 4, 8
RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}

# TAISURE exposes DeepSeek reasoning models behind bare ids. They can spend the
# small default response budget entirely on reasoning_content and return empty
# final content unless we give them the same headroom as the DeepSeek-direct path.
_THINKING_MODEL_KEYS = ("v4-pro", "v4-flash", "reasoner")


def _needs_thinking(model: str) -> bool:
    m = (model or "").lower()
    return any(k in m for k in _THINKING_MODEL_KEYS)


_usage_state = threading.local()


def get_last_usage() -> Dict[str, Any]:
    """Return token usage from the most recent chat_completion call."""
    return dict(getattr(_usage_state, "last_usage", {}))


def reset_usage() -> None:
    """Clear stored usage (useful before a sequence of calls you want to meter)."""
    _usage_state.last_usage = {}


def get_api_key() -> str:
    key = os.environ.get("TAISURE_API_KEY", "")
    if not key:
        raise RuntimeError(
            "TAISURE_API_KEY environment variable is not set. "
            "Set it to use TAISURE-hosted models (https://taisure.com)."
        )
    return key


def _strip_prefix(model: str) -> str:
    if model.startswith("taisure/"):
        return model[len("taisure/") :]
    return model


def chat_completion(
    *,
    messages: List[Dict[str, str]],
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = DEFAULT_TEMPERATURE,
    timeout_seconds: float = 120,
) -> str:
    """
    Call the TAISURE chat completion API and return the assistant's response text.

    Args:
        messages: List of {"role": "system"|"user"|"assistant", "content": "..."}
        model: TAISURE model id, with or without the `taisure/` routing prefix
        max_tokens: Max tokens in response
        temperature: Sampling temperature
        timeout_seconds: HTTP timeout

    Returns:
        Assistant response text
    """
    api_key = get_api_key()
    model = _strip_prefix(model)

    is_thinking = _needs_thinking(model)
    effective_max_tokens = max_tokens
    effective_timeout = timeout_seconds
    if is_thinking and max_tokens < 16384:
        logger.info(
            "TAISURE %s is a reasoning model; bumping max_tokens %d → 16384",
            model,
            max_tokens,
        )
        effective_max_tokens = 16384
    if is_thinking and timeout_seconds < 300:
        effective_timeout = 300

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    url = f"{API_BASE}/chat/completions"

    # Some TAISURE-hosted models (e.g. claude-*, certain reasoning models) reject
    # `temperature` outright with a 400 instead of ignoring it the way OpenRouter
    # does. We send it by default but transparently retry without it when the
    # gateway complains, so callers don't need a per-model parameter allowlist.
    drop_temperature = False

    def _build_data() -> bytes:
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": effective_max_tokens,
        }
        if not drop_temperature:
            payload["temperature"] = temperature
        return json.dumps(payload).encode("utf-8")

    last_exc: Optional[Exception] = None
    result: Dict[str, Any] = {}
    for attempt in range(MAX_RETRIES):
        req = request.Request(url, data=_build_data(), headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=effective_timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            break  # success
        except error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                pass
            # Retry without `temperature` if the model rejects it. This is a
            # deterministic parameter fix that fires on the first call, so the
            # one attempt it costs still leaves headroom for transient retries.
            if exc.code == 400 and not drop_temperature and "temperature" in body.lower():
                logger.info("TAISURE model %s rejected `temperature`; retrying without it", model)
                drop_temperature = True
                continue
            last_exc = RuntimeError(f"TAISURE API error {exc.code}: {body}")
            if exc.code in RETRYABLE_HTTP_CODES and attempt < MAX_RETRIES - 1:
                delay = RETRY_BACKOFF_BASE * (2**attempt)
                logger.warning(
                    "TAISURE %s (attempt %d/%d), retrying in %.0fs...",
                    exc.code,
                    attempt + 1,
                    MAX_RETRIES,
                    delay,
                )
                time.sleep(delay)
                continue
            logger.error("TAISURE API error %s: %s", exc.code, body)
            raise last_exc from exc
        except (error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
            last_exc = RuntimeError(f"TAISURE network error: {exc}")
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_BACKOFF_BASE * (2**attempt)
                logger.warning(
                    "TAISURE network error (attempt %d/%d), retrying in %.0fs: %s",
                    attempt + 1,
                    MAX_RETRIES,
                    delay,
                    exc,
                )
                time.sleep(delay)
                continue
            raise last_exc from exc
    else:
        raise last_exc or RuntimeError("TAISURE API failed after retries")

    # Store usage for callers that need token accounting
    _usage_state.last_usage = dict(result.get("usage", {}))

    choices = result.get("choices", [])
    if not choices:
        raise RuntimeError(f"TAISURE returned no choices (model='{model}'): {result}")

    message = choices[0].get("message", {}) or {}
    content = message.get("content") or ""
    if not content.strip():
        finish_reason = choices[0].get("finish_reason", "?")
        usage = result.get("usage", {})
        # Some reasoning models route their chain-of-thought through
        # reasoning_content; an empty content with non-empty reasoning usually
        # means the answer was cut off by max_tokens.
        had_reasoning = bool((message.get("reasoning_content") or "").strip())
        raise RuntimeError(
            f"TAISURE returned empty content (model='{model}', "
            f"finish_reason={finish_reason}, usage={usage}, "
            f"had_reasoning_content={had_reasoning}). "
            f"For reasoning models try a larger max_tokens."
        )
    return content


def query_with_system_prompt(
    *,
    system_prompt: str,
    user_message: str,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = DEFAULT_TEMPERATURE,
    timeout_seconds: float = 120,
) -> str:
    """Convenience: send system + user message, return assistant text."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    return chat_completion(
        messages=messages,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout_seconds=timeout_seconds,
    )
