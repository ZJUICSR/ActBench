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
import lib_llm_config  # noqa: E402
import lib_openai_compatible  # noqa: E402


def test_lib_llm_routes_configured_private_gateway_models(monkeypatch: Any, tmp_path: Path) -> None:
    config_path = tmp_path / "llm_backends.local.yaml"
    config_path.write_text(
        """
providers:
  private:
    prefix: private/
    api_key_env: ACTBENCH_PRIVATE_GATEWAY_API_KEY
    base_url_env: ACTBENCH_PRIVATE_GATEWAY_BASE_URL
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("ACTBENCH_LLM_BACKENDS_CONFIG", str(config_path))
    seen: dict[str, Any] = {}

    def fake_chat_completion(**kwargs: Any) -> str:
        seen.update(kwargs)
        return '{"ok": true}'

    monkeypatch.setattr(lib_openai_compatible, "chat_completion", fake_chat_completion)
    monkeypatch.setattr(
        lib_openai_compatible,
        "get_last_usage",
        lambda: {"prompt_tokens": 7, "completion_tokens": 3},
    )
    monkeypatch.setattr(lib_llm.lib_openrouter, "get_last_usage", lambda: {})
    monkeypatch.setattr(lib_llm.lib_deepseek, "get_last_usage", lambda: {})

    response = lib_llm.chat_completion(
        messages=[{"role": "user", "content": "hello"}],
        model="private/gpt-5.5",
        max_tokens=123,
        temperature=0.2,
        trace_role="test",
    )

    assert response == '{"ok": true}'
    assert seen["model"] == "private/gpt-5.5"
    assert seen["provider"].name == "private"
    assert seen["max_tokens"] == 123
    assert seen["temperature"] == 0.2
    usage = lib_llm.get_last_usage()
    assert usage["input_tokens"] == 7
    assert usage["output_tokens"] == 3
    assert usage["total_tokens"] == 10


def test_openai_compatible_chat_completion_posts_payload(monkeypatch: Any) -> None:
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

    provider = lib_llm_config.ProviderConfig(
        name="private",
        prefix="private/",
        api_key_env="ACTBENCH_PRIVATE_GATEWAY_API_KEY",
        base_url_env="ACTBENCH_PRIVATE_GATEWAY_BASE_URL",
    )
    monkeypatch.setenv("ACTBENCH_PRIVATE_GATEWAY_API_KEY", "test-key")
    monkeypatch.setenv("ACTBENCH_PRIVATE_GATEWAY_BASE_URL", "https://private-gateway.example/v1")
    monkeypatch.setattr(lib_openai_compatible.request, "urlopen", fake_urlopen)
    lib_openai_compatible.reset_usage()

    response = lib_openai_compatible.chat_completion(
        messages=[{"role": "user", "content": "hello"}],
        model="private/gpt-5.5",
        provider=provider,
        max_tokens=99,
        temperature=0.4,
        timeout_seconds=12,
    )

    assert response == "done"
    assert captured["url"] == "https://private-gateway.example/v1/chat/completions"
    assert captured["timeout"] == 12
    assert captured["authorization"] == "Bearer test-key"
    assert captured["payload"] == {
        "model": "gpt-5.5",
        "messages": [{"role": "user", "content": "hello"}],
        "max_tokens": 99,
        "temperature": 0.4,
    }
    assert lib_openai_compatible.get_last_usage()["total_tokens"] == 7


def test_openai_compatible_api_base_accepts_full_chat_completions_url() -> None:
    assert (
        lib_openai_compatible._chat_completions_url(
            "https://private-gateway.example/v1/chat/completions"
        )
        == "https://private-gateway.example/v1/chat/completions"
    )
