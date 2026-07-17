from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import lib_llm  # noqa: E402
import lib_zjuicsr  # noqa: E402


def test_lib_llm_routes_zjuicsr_models(monkeypatch: Any) -> None:
    seen: dict[str, Any] = {}

    def fake_chat_completion(**kwargs: Any) -> str:
        seen.update(kwargs)
        return '{"ok": true}'

    monkeypatch.setattr(lib_zjuicsr, "chat_completion", fake_chat_completion)
    monkeypatch.setattr(lib_zjuicsr, "get_last_usage", lambda: {"prompt_tokens": 7, "completion_tokens": 3})
    monkeypatch.setattr(lib_llm.lib_openrouter, "get_last_usage", lambda: {})
    monkeypatch.setattr(lib_llm.lib_deepseek, "get_last_usage", lambda: {})
    monkeypatch.setattr(lib_llm.lib_taisure, "get_last_usage", lambda: {})

    response = lib_llm.chat_completion(
        messages=[{"role": "user", "content": "hello"}],
        model="zjuicsr/gpt-5.5",
        max_tokens=123,
        temperature=0.2,
        trace_role="test",
    )

    assert response == '{"ok": true}'
    assert seen["model"] == "zjuicsr/gpt-5.5"
    assert seen["max_tokens"] == 123
    assert seen["temperature"] == 0.2
    usage = lib_llm.get_last_usage()
    assert usage["input_tokens"] == 7
    assert usage["output_tokens"] == 3
    assert usage["total_tokens"] == 10


def test_zjuicsr_chat_completion_posts_openai_compatible_payload(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
            return False

        def read(self) -> bytes:
            return json.dumps(
                {
                    "choices": [{"message": {"content": "done"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
                }
            ).encode("utf-8")

    def fake_urlopen(req: Any, timeout: float) -> FakeResponse:
        captured["url"] = req.full_url
        captured["timeout"] = timeout
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        captured["authorization"] = req.headers.get("Authorization")
        return FakeResponse()

    monkeypatch.setenv("ZJUICSR_API_KEY", "test-key")
    monkeypatch.setenv("ZJUICSR_API_BASE", "https://zjuicsr.example/v1")
    monkeypatch.setattr(lib_zjuicsr.request, "urlopen", fake_urlopen)
    lib_zjuicsr.reset_usage()

    response = lib_zjuicsr.chat_completion(
        messages=[{"role": "user", "content": "hello"}],
        model="zjuicsr/gpt-5.5",
        max_tokens=99,
        temperature=0.4,
        timeout_seconds=12,
    )

    assert response == "done"
    assert captured["url"] == "https://zjuicsr.example/v1/chat/completions"
    assert captured["timeout"] == 12
    assert captured["authorization"] == "Bearer test-key"
    assert captured["payload"] == {
        "model": "gpt-5.5",
        "messages": [{"role": "user", "content": "hello"}],
        "max_tokens": 99,
        "temperature": 0.4,
    }
    assert lib_zjuicsr.get_last_usage()["total_tokens"] == 7


def test_zjuicsr_api_base_accepts_full_chat_completions_url(monkeypatch: Any) -> None:
    monkeypatch.setenv("ZJUICSR_API_BASE", "https://zjuicsr.example/v1/chat/completions")

    assert lib_zjuicsr._chat_completions_url(lib_zjuicsr.get_api_base()) == (
        "https://zjuicsr.example/v1/chat/completions"
    )
