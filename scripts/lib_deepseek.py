"""
ClawEval DeepSeek API Client.

OpenAI-compatible client for DeepSeek models (deepseek-v4-pro / deepseek-chat /
deepseek-reasoner) served at api.deepseek.com. Target models still go through
OpenClaw, not this client.
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
DEFAULT_MAX_TOKENS = 8192  # generous default; v4 reasoning models eat most of this on thinking
DEFAULT_TEMPERATURE = 0.7
API_BASE = "https://api.deepseek.com/v1"
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2.0
RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}

# Models whose answer-quality requires thinking-mode to be explicitly enabled.
# DeepSeek docs: v4-pro / v4-flash route thinking via extra_body.thinking.enabled.
# Older `deepseek-reasoner` is thinking-mode by default but we set it for safety.
_THINKING_MODEL_KEYS = ("v4-pro", "v4-flash", "reasoner")


def _needs_thinking(model: str) -> bool:
    m = (model or "").lower()
    return any(k in m for k in _THINKING_MODEL_KEYS)


_usage_state = threading.local()


def get_last_usage() -> Dict[str, Any]:
    return dict(getattr(_usage_state, "last_usage", {}))


def reset_usage() -> None:
    _usage_state.last_usage = {}


def get_api_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        raise RuntimeError(
            "DEEPSEEK_API_KEY environment variable is not set. "
            "Set it to use DeepSeek (api.deepseek.com)."
        )
    return key


def _strip_prefix(model: str) -> str:
    if model.startswith("deepseek/"):
        return model[len("deepseek/") :]
    return model


def chat_completion(
    *,
    messages: List[Dict[str, str]],
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = DEFAULT_TEMPERATURE,
    timeout_seconds: float = 120,
) -> str:
    api_key = get_api_key()
    model = _strip_prefix(model)

    is_thinking = _needs_thinking(model)

    # Reasoning models burn a large fraction of the budget on the chain-of-
    # thought before producing the final `content`. If the caller passed a
    # small budget (e.g. lib_reward's 2048 for the judge), bump it so the
    # answer isn't truncated to empty.
    effective_max_tokens = max_tokens
    if is_thinking and max_tokens < 16384:
        logger.info(
            "DeepSeek %s is a reasoning model; bumping max_tokens %d → 16384", model, max_tokens
        )
        effective_max_tokens = 16384

    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": effective_max_tokens,
    }
    if is_thinking:
        # Per DeepSeek docs: thinking mode silently ignores temperature / top_p /
        # presence_penalty / frequency_penalty. Drop them entirely so the payload
        # matches what the API actually honors and judge variance becomes pure
        # sampling noise on the reasoning chain.
        payload["thinking"] = {"type": "enabled"}
        payload["reasoning_effort"] = "high"
    else:
        payload["temperature"] = temperature
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    url = f"{API_BASE}/chat/completions"
    data = json.dumps(payload).encode("utf-8")

    last_exc: Optional[Exception] = None
    result: Dict[str, Any] = {}
    for attempt in range(MAX_RETRIES):
        req = request.Request(url, data=data, headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=timeout_seconds) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            break
        except error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                pass
            last_exc = RuntimeError(f"DeepSeek API error {exc.code}: {body}")
            if exc.code in RETRYABLE_HTTP_CODES and attempt < MAX_RETRIES - 1:
                delay = RETRY_BACKOFF_BASE * (2**attempt)
                logger.warning(
                    "DeepSeek %s (attempt %d/%d), retrying in %.0fs...",
                    exc.code,
                    attempt + 1,
                    MAX_RETRIES,
                    delay,
                )
                time.sleep(delay)
                continue
            logger.error("DeepSeek API error %s: %s", exc.code, body)
            raise last_exc from exc
        except (error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
            last_exc = RuntimeError(f"DeepSeek network error: {exc}")
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_BACKOFF_BASE * (2**attempt)
                logger.warning(
                    "DeepSeek network error (attempt %d/%d), retrying in %.0fs: %s",
                    attempt + 1,
                    MAX_RETRIES,
                    delay,
                    exc,
                )
                time.sleep(delay)
                continue
            raise last_exc from exc
    else:
        raise last_exc or RuntimeError("DeepSeek API failed after retries")

    _usage_state.last_usage = dict(result.get("usage", {}))

    choices = result.get("choices", [])
    if not choices:
        raise RuntimeError(f"DeepSeek returned no choices (model='{model}'): {result}")

    message = choices[0].get("message", {}) or {}
    content = message.get("content") or ""
    if not content.strip():
        finish_reason = choices[0].get("finish_reason", "?")
        usage = result.get("usage", {})
        # Reasoning models put thinking in reasoning_content; if content is empty
        # but reasoning_content has data, the answer was likely cut off by max_tokens.
        had_reasoning = bool((message.get("reasoning_content") or "").strip())
        raise RuntimeError(
            f"DeepSeek returned empty content (model='{model}', "
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
