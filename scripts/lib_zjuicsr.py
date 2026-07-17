"""
ClawEval ZJUICSR API Client.

OpenAI-compatible client for ZJUICSR-hosted support models such as gpt-5.5.
Target-model execution still goes through OpenClaw; this client is only for
ActBench support-model calls such as reward judges.

Callers select this backend with an explicit ``zjuicsr/`` prefix, e.g.
``zjuicsr/gpt-5.5``. The prefix is stripped before sending the model id to the
OpenAI-compatible endpoint.
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

DEFAULT_MODEL = "gpt-5.5"
DEFAULT_MAX_TOKENS = 4096
DEFAULT_TEMPERATURE = 0.7
DEFAULT_API_BASE = "https://router.zjuicsr.cn/v1/chat/completions"
API_BASE_ENV_VARS = (
    "ZJUICSR_API_BASE",
    "ZJUICSR_BASE_URL",
    "ZJUICSR_OPENAI_BASE_URL",
)
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2.0
RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}

_usage_state = threading.local()


def get_last_usage() -> Dict[str, Any]:
    """Return token usage from the most recent chat_completion call."""

    return dict(getattr(_usage_state, "last_usage", {}))


def reset_usage() -> None:
    """Clear stored usage (useful before a sequence of calls you want to meter)."""

    _usage_state.last_usage = {}


def get_api_key() -> str:
    key = os.environ.get("ZJUICSR_API_KEY", "")
    if not key:
        raise RuntimeError(
            "ZJUICSR_API_KEY environment variable is not set. "
            "Set it to use ZJUICSR-hosted ActBench support models."
        )
    return key


def get_api_base() -> str:
    for env_name in API_BASE_ENV_VARS:
        value = os.environ.get(env_name, "").strip()
        if value:
            return value.rstrip("/")
    return DEFAULT_API_BASE.rstrip("/")


def _chat_completions_url(api_base: str) -> str:
    base = api_base.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def _strip_prefix(model: str) -> str:
    if model.startswith("zjuicsr/"):
        return model[len("zjuicsr/") :]
    return model


def _content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        pieces: list[str] = []
        for item in content:
            if isinstance(item, str):
                pieces.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    pieces.append(text)
        return "".join(pieces)
    return str(content)


def chat_completion(
    *,
    messages: List[Dict[str, str]],
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = DEFAULT_TEMPERATURE,
    timeout_seconds: float = 120,
) -> str:
    """
    Call the ZJUICSR OpenAI-compatible chat completion API.

    Args:
        messages: List of {"role": "system"|"user"|"assistant", "content": "..."}
        model: ZJUICSR model id, with or without the ``zjuicsr/`` routing prefix
        max_tokens: Max tokens in response
        temperature: Sampling temperature
        timeout_seconds: HTTP timeout

    Returns:
        Assistant response text.
    """

    api_key = get_api_key()
    model = _strip_prefix(model)
    url = _chat_completions_url(get_api_base())

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # Some OpenAI-compatible gateways reject temperature for newer/reasoning
    # models. Send it first for parity with the existing judge clients, then
    # deterministically retry without it if the server says it is unsupported.
    drop_temperature = False

    def _build_data() -> bytes:
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if not drop_temperature:
            payload["temperature"] = temperature
        return json.dumps(payload).encode("utf-8")

    last_exc: Optional[Exception] = None
    result: Dict[str, Any] = {}
    for attempt in range(MAX_RETRIES):
        req = request.Request(url, data=_build_data(), headers=headers, method="POST")
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
            if exc.code == 400 and not drop_temperature and "temperature" in body.lower():
                logger.info("ZJUICSR model %s rejected `temperature`; retrying without it", model)
                drop_temperature = True
                continue
            last_exc = RuntimeError(f"ZJUICSR API error {exc.code}: {body}")
            if exc.code in RETRYABLE_HTTP_CODES and attempt < MAX_RETRIES - 1:
                delay = RETRY_BACKOFF_BASE * (2**attempt)
                logger.warning(
                    "ZJUICSR %s (attempt %d/%d), retrying in %.0fs...",
                    exc.code,
                    attempt + 1,
                    MAX_RETRIES,
                    delay,
                )
                time.sleep(delay)
                continue
            logger.error("ZJUICSR API error %s: %s", exc.code, body)
            raise last_exc from exc
        except (error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
            last_exc = RuntimeError(f"ZJUICSR network error: {exc}")
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_BACKOFF_BASE * (2**attempt)
                logger.warning(
                    "ZJUICSR network error (attempt %d/%d), retrying in %.0fs: %s",
                    attempt + 1,
                    MAX_RETRIES,
                    delay,
                    exc,
                )
                time.sleep(delay)
                continue
            raise last_exc from exc
    else:
        raise last_exc or RuntimeError("ZJUICSR API failed after retries")

    _usage_state.last_usage = dict(result.get("usage", {}))

    choices = result.get("choices", [])
    if not choices:
        raise RuntimeError(f"ZJUICSR returned no choices (model='{model}'): {result}")

    message = choices[0].get("message", {}) or {}
    content = _content_to_text(message.get("content"))
    if not content.strip():
        finish_reason = choices[0].get("finish_reason", "?")
        usage = result.get("usage", {})
        raise RuntimeError(
            f"ZJUICSR returned empty content (model='{model}', "
            f"finish_reason={finish_reason}, usage={usage})."
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
