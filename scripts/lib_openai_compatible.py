"""
Generic OpenAI-compatible support-model client for ActBench.

Private gateway identity lives in ignored local provider config. This module only
implements the shared chat-completions protocol used by those gateways.
"""

from __future__ import annotations

import http.client
import json
import logging
import threading
import time
from typing import Any, Dict, List, Optional

from urllib import error, request

from lib_llm_config import ProviderConfig

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 4096
DEFAULT_TEMPERATURE = 0.7
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2.0
RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}

_usage_state = threading.local()


def get_last_usage() -> Dict[str, Any]:
    """Return token usage from the most recent chat_completion call."""

    return dict(getattr(_usage_state, "last_usage", {}))


def reset_usage() -> None:
    """Clear stored usage for the current thread."""

    _usage_state.last_usage = {}


def chat_completion(
    *,
    messages: List[Dict[str, str]],
    model: str,
    provider: ProviderConfig,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = DEFAULT_TEMPERATURE,
    timeout_seconds: float = 120,
) -> str:
    """Call a configured OpenAI-compatible chat-completions endpoint."""

    api_key = provider.api_key()
    request_model = _strip_prefix(model, provider) if provider.strip_prefix else model
    url = _chat_completions_url(provider.api_base())

    is_thinking = _needs_thinking(request_model, provider)
    effective_max_tokens = max_tokens
    effective_timeout = timeout_seconds
    if is_thinking and max_tokens < provider.min_thinking_max_tokens:
        logger.info(
            "%s %s is a reasoning model; bumping max_tokens %d → %d",
            provider.display_name,
            request_model,
            max_tokens,
            provider.min_thinking_max_tokens,
        )
        effective_max_tokens = provider.min_thinking_max_tokens
    if is_thinking and timeout_seconds < provider.min_thinking_timeout_seconds:
        effective_timeout = provider.min_thinking_timeout_seconds

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    drop_temperature = False

    def _build_data() -> bytes:
        payload: Dict[str, Any] = {
            "model": request_model,
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
            break
        except error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                pass
            if (
                exc.code == 400
                and provider.retry_without_temperature
                and not drop_temperature
                and "temperature" in body.lower()
            ):
                logger.info(
                    "%s model %s rejected `temperature`; retrying without it",
                    provider.display_name,
                    request_model,
                )
                drop_temperature = True
                continue
            last_exc = RuntimeError(f"{provider.display_name} API error {exc.code}: {body}")
            if exc.code in RETRYABLE_HTTP_CODES and attempt < MAX_RETRIES - 1:
                delay = RETRY_BACKOFF_BASE * (2**attempt)
                logger.warning(
                    "%s %s (attempt %d/%d), retrying in %.0fs...",
                    provider.display_name,
                    exc.code,
                    attempt + 1,
                    MAX_RETRIES,
                    delay,
                )
                time.sleep(delay)
                continue
            logger.error("%s API error %s: %s", provider.display_name, exc.code, body)
            raise last_exc from exc
        except (error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
            last_exc = RuntimeError(f"{provider.display_name} network error: {exc}")
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_BACKOFF_BASE * (2**attempt)
                logger.warning(
                    "%s network error (attempt %d/%d), retrying in %.0fs: %s",
                    provider.display_name,
                    attempt + 1,
                    MAX_RETRIES,
                    delay,
                    exc,
                )
                time.sleep(delay)
                continue
            raise last_exc from exc
    else:
        raise last_exc or RuntimeError(f"{provider.display_name} API failed after retries")

    _usage_state.last_usage = dict(result.get("usage", {}))

    choices = result.get("choices", [])
    if not choices:
        raise RuntimeError(
            f"{provider.display_name} returned no choices (model='{request_model}'): {result}"
        )

    message = choices[0].get("message", {}) or {}
    content = _content_to_text(message.get("content"))
    if not content.strip():
        finish_reason = choices[0].get("finish_reason", "?")
        usage = result.get("usage", {})
        raise RuntimeError(
            f"{provider.display_name} returned empty content (model='{request_model}', "
            f"finish_reason={finish_reason}, usage={usage})."
        )
    return content


def query_with_system_prompt(
    *,
    system_prompt: str,
    user_message: str,
    model: str,
    provider: ProviderConfig,
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
        provider=provider,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout_seconds=timeout_seconds,
    )


def _chat_completions_url(api_base: str) -> str:
    base = api_base.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def _strip_prefix(model: str, provider: ProviderConfig) -> str:
    if model.lower().startswith(provider.prefix.lower()):
        return model[len(provider.prefix) :]
    return model


def _needs_thinking(model: str, provider: ProviderConfig) -> bool:
    m = (model or "").lower()
    return any(key.lower() in m for key in provider.thinking_model_keys)


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
