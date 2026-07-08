"""
LLM backend router for ActBench support models.

Dispatches based on the model id prefix:
  - "taisure/..."                                          -> TAISURE (taisure.com)
  - "deepseek/...", "deepseek-..."                         -> DeepSeek (api.deepseek.com)
  - everything else                                        -> OpenRouter

Target models (run via OpenClaw) are unaffected — they don't use this module.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

import lib_deepseek
import lib_openrouter
import lib_taisure
from lib_training_artifacts import record_model_call

TAISURE_PREFIXES = ("taisure/",)
DEEPSEEK_PREFIXES = ("deepseek/", "deepseek-")


def _is_taisure(model: str) -> bool:
    m = (model or "").lower()
    return any(m.startswith(p) for p in TAISURE_PREFIXES)


def _is_deepseek(model: str) -> bool:
    m = (model or "").lower()
    return any(m.startswith(p) for p in DEEPSEEK_PREFIXES)


def _backend(model: str):
    # Order matters: a `taisure/deepseek-v4-pro` id must route to TAISURE, not
    # the DeepSeek-direct backend, so check the explicit taisure/ prefix first.
    if _is_taisure(model):
        return lib_taisure
    if _is_deepseek(model):
        return lib_deepseek
    return lib_openrouter


def chat_completion(
    *,
    messages: List[Dict[str, str]],
    model: str,
    **kwargs: Any,
) -> str:
    trace_role = str(kwargs.pop("trace_role", "unknown"))
    trace_metadata = kwargs.pop("trace_metadata", {})
    backend = _backend(model)
    request_payload = {
        "messages": messages,
        "model": model,
        "kwargs": dict(kwargs),
    }
    start = time.perf_counter()
    try:
        response = backend.chat_completion(messages=messages, model=model, **kwargs)
        usage = normalize_usage(backend.get_last_usage())
        record_model_call(
            role=trace_role,
            model=model,
            request_payload=request_payload,
            response=response,
            usage=usage,
            duration_seconds=round(time.perf_counter() - start, 4),
            metadata=(
                trace_metadata if isinstance(trace_metadata, dict) else {"value": trace_metadata}
            ),
        )
        return response
    except Exception as exc:
        record_model_call(
            role=trace_role,
            model=model,
            request_payload=request_payload,
            response=None,
            usage=normalize_usage(backend.get_last_usage()),
            duration_seconds=round(time.perf_counter() - start, 4),
            metadata=(
                trace_metadata if isinstance(trace_metadata, dict) else {"value": trace_metadata}
            ),
            error=str(exc),
        )
        raise


def query_with_system_prompt(
    *,
    system_prompt: str,
    user_message: str,
    model: str,
    **kwargs: Any,
) -> str:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    return chat_completion(
        messages=messages,
        model=model,
        **kwargs,
    )


def normalize_usage(usage: Dict[str, Any] | None) -> Dict[str, Any]:
    """Normalize provider-specific usage fields into ClawEval's common shape."""
    usage = usage or {}
    input_tokens = int(
        usage.get("input_tokens") or usage.get("prompt_tokens") or usage.get("input") or 0
    )
    output_tokens = int(
        usage.get("output_tokens") or usage.get("completion_tokens") or usage.get("output") or 0
    )
    cache_read_tokens = int(
        usage.get("cache_read_tokens") or usage.get("cacheRead") or usage.get("cache_read") or 0
    )
    cache_write_tokens = int(
        usage.get("cache_write_tokens") or usage.get("cacheWrite") or usage.get("cache_write") or 0
    )
    total_tokens = int(
        usage.get("total_tokens")
        or usage.get("totalTokens")
        or usage.get("total")
        or (input_tokens + output_tokens + cache_read_tokens + cache_write_tokens)
    )
    cost = usage.get("cost") or {}
    cost_usd = usage.get("cost_usd")
    if cost_usd is None and isinstance(cost, dict):
        cost_usd = cost.get("total", 0.0)

    normalized = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_tokens": cache_read_tokens,
        "cache_write_tokens": cache_write_tokens,
        "total_tokens": total_tokens,
        "cost_usd": float(cost_usd or 0.0),
        "request_count": int(usage.get("request_count") or (1 if usage else 0)),
    }
    # Keep legacy names so existing attacker/search accounting continues to work.
    normalized["prompt_tokens"] = input_tokens
    normalized["completion_tokens"] = output_tokens
    return normalized


def get_last_usage() -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    merged.update(lib_openrouter.get_last_usage())
    merged.update(lib_deepseek.get_last_usage())
    merged.update(lib_taisure.get_last_usage())
    return normalize_usage(merged)


def reset_usage() -> None:
    lib_openrouter.reset_usage()
    lib_deepseek.reset_usage()
    lib_taisure.reset_usage()
