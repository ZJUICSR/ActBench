"""
ClawEval OpenRouter API Client.

Direct HTTP client for ActBench support-model calls. Target-model execution goes
through OpenClaw, not this client.
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

DEFAULT_MODEL = "deepseek/deepseek-v4-pro"
DEFAULT_MAX_TOKENS = 4096
DEFAULT_TEMPERATURE = 0.7
API_BASE = "https://openrouter.ai/api/v1"
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2.0  # seconds; delays: 2, 4, 8
RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}

# Thread-local storage for the most recent API call's usage stats.
# Callers can read this via get_last_usage() after any chat_completion call.
_usage_state = threading.local()


def get_last_usage() -> Dict[str, Any]:
    """Return token usage from the most recent chat_completion call.

    Typical keys: prompt_tokens, completion_tokens, total_tokens.
    Returns an empty dict if no usage data is available.
    """
    return dict(getattr(_usage_state, "last_usage", {}))


def reset_usage() -> None:
    """Clear stored usage (useful before a sequence of calls you want to meter)."""
    _usage_state.last_usage = {}


def get_api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        raise RuntimeError(
            "OPENROUTER_API_KEY environment variable is not set. "
            "Set it to use OpenRouter-hosted ActBench support models."
        )
    return key


def chat_completion(
    *,
    messages: List[Dict[str, str]],
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = DEFAULT_TEMPERATURE,
    timeout_seconds: float = 120,
) -> str:
    """
    Call OpenRouter chat completion API and return the assistant's response text.

    Args:
        messages: List of {"role": "system"|"user"|"assistant", "content": "..."}
        model: OpenRouter model ID (without openrouter/ prefix)
        max_tokens: Max tokens in response
        temperature: Sampling temperature
        timeout_seconds: HTTP timeout

    Returns:
        Assistant response text
    """
    api_key = get_api_key()

    # Strip openrouter/ prefix if present
    if model.startswith("openrouter/"):
        model = model[len("openrouter/") :]

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://claweval.zjuicsr.com",
        "X-Title": "ClawEval",
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
            break  # success
        except error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                pass
            last_exc = RuntimeError(f"OpenRouter API error {exc.code}: {body}")
            if exc.code in RETRYABLE_HTTP_CODES and attempt < MAX_RETRIES - 1:
                delay = RETRY_BACKOFF_BASE * (2**attempt)
                logger.warning(
                    "OpenRouter %s (attempt %d/%d), retrying in %.0fs...",
                    exc.code,
                    attempt + 1,
                    MAX_RETRIES,
                    delay,
                )
                time.sleep(delay)
                continue
            logger.error("OpenRouter API error %s: %s", exc.code, body)
            raise last_exc from exc
        except (error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
            last_exc = RuntimeError(f"OpenRouter network error: {exc}")
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_BACKOFF_BASE * (2**attempt)
                logger.warning(
                    "OpenRouter network error (attempt %d/%d), retrying in %.0fs: %s",
                    attempt + 1,
                    MAX_RETRIES,
                    delay,
                    exc,
                )
                time.sleep(delay)
                continue
            raise last_exc from exc
    else:
        raise last_exc or RuntimeError("OpenRouter API failed after retries")

    # Store usage for callers that need token accounting
    _usage_state.last_usage = dict(result.get("usage", {}))

    choices = result.get("choices", [])
    if not choices:
        logger.warning("OpenRouter returned no choices: %s", result)
        return ""

    return choices[0].get("message", {}).get("content", "")


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
