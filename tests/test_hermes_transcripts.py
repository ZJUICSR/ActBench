from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from benchmark.backends.base import BackendRunContext  # noqa: E402
from benchmark.backends.hermes import (  # noqa: E402
    HermesBackend,
    _normalize_hermes_export_to_transcript,
    _parse_hermes_export_jsonl,
)
from lib_reward import (
    _check_dangerous_commands,
    _check_skill_invocation,
    _transcript_to_text,
)  # noqa: E402
from lib_tasks import Task  # noqa: E402


def _task() -> Task:
    return Task(
        task_id="task_fake",
        name="Fake task",
        category="",
        grading_type="automated",
        timeout_seconds=30,
        workspace_files=[{"path": "README.md", "content": "hello"}],
        prompt="Say hello.",
        expected_behavior="",
        grading_criteria=[],
        frontmatter={},
    )


def _context(tmp_path: Path) -> BackendRunContext:
    return BackendRunContext(
        backend="hermes",
        model="test/model",
        run_id="run_001",
        run_root=tmp_path / "run_root",
        skill_dir=ROOT,
        agent_id="bench-test-model",
        agent_workspace=tmp_path / "agent_workspace",
        timeout_multiplier=1.0,
        verbose=False,
    )


def _configure_hermes_test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACTBENCH_HERMES_BIN", "hermes")
    monkeypatch.setenv("ACTBENCH_HERMES_ENABLE_ACTBENCH_MCP", "0")
    monkeypatch.delenv("ACTBENCH_HERMES_PROVIDER", raising=False)
    monkeypatch.delenv("ACTBENCH_HERMES_MODEL", raising=False)
    monkeypatch.delenv("ACTBENCH_HERMES_TOOLSETS", raising=False)
    monkeypatch.delenv("ACTBENCH_HERMES_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("ACTBENCH_HERMES_HOME_ROOT", raising=False)


def _session_jsonl(
    workspace: Path, *, model: str = "test/model", messages: list[dict[str, Any]]
) -> str:
    return json.dumps(
        {
            "id": "session-1",
            "source": "cli",
            "model": model,
            "cwd": str(workspace),
            "started_at": 1000.0,
            "last_active": 1005.0,
            "message_count": len(messages),
            "tool_call_count": 1,
            "messages": messages,
        },
        ensure_ascii=False,
    )


def test_hermes_export_normalizes_text_tool_calls_and_tool_results(tmp_path: Path) -> None:
    raw = _session_jsonl(
        tmp_path,
        messages=[
            {"role": "user", "content": "Read README.md"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {
                            "name": "read_file",
                            "arguments": '{"path": "README.md"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "tool_name": "read_file",
                "content": "hello",
            },
            {"role": "assistant", "content": "done"},
        ],
    )
    records, errors = _parse_hermes_export_jsonl(raw)

    transcript = _normalize_hermes_export_to_transcript(records)

    assert errors == []
    assert transcript[0] == {
        "type": "message",
        "message": {"role": "user", "content": ["Read README.md"]},
    }
    assert transcript[1]["message"]["content"] == [
        {
            "type": "toolCall",
            "name": "read_file",
            "arguments": {"path": "README.md"},
            "id": "call_1",
        }
    ]
    assert transcript[2]["message"]["role"] == "toolResult"
    assert transcript[2]["message"]["content"][0]["tool_call_id"] == "call_1"
    assert transcript[2]["message"]["content"][0]["name"] == "read_file"
    assert transcript[3]["message"]["content"] == [{"type": "text", "text": "done"}]


def test_hermes_export_parses_json_string_tool_calls_and_raw_arguments(tmp_path: Path) -> None:
    tool_calls = json.dumps(
        [
            {
                "call_id": "call_raw",
                "type": "function",
                "function": {"name": "run_shell", "arguments": "not-json"},
            }
        ]
    )
    raw = _session_jsonl(
        tmp_path,
        messages=[{"role": "assistant", "content": [], "tool_calls": tool_calls}],
    )
    records, errors = _parse_hermes_export_jsonl(raw)

    transcript = _normalize_hermes_export_to_transcript(records)

    assert errors == []
    block = transcript[0]["message"]["content"][0]
    assert block["type"] == "toolCall"
    assert block["name"] == "run_shell"
    assert block["id"] == "call_raw"
    assert block["arguments"] == {"raw": "not-json"}


def test_hermes_tool_call_arguments_are_reward_compatible(tmp_path: Path) -> None:
    transcript = [
        {
            "type": "message",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "toolCall",
                        "name": "run_shell",
                        "arguments": {"command": "rm -rf /tmp/x"},
                    }
                ],
            },
        }
    ]

    transcript_text = _transcript_to_text(transcript)

    assert _check_dangerous_commands(transcript_text, tmp_path) > 0
    assert (
        _check_skill_invocation(
            {},
            transcript_text,
            transcript=transcript,
            malicious_skill_names=["run_shell"],
        )
        == 1.0
    )


def test_hermes_backend_uses_sessions_export_transcript(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.hermes as hermes_module

    _configure_hermes_test_env(monkeypatch)
    monkeypatch.setattr(hermes_module.shutil, "which", lambda _: "/usr/bin/hermes")
    backend = HermesBackend()

    def fake_run(**kwargs: Any) -> subprocess.CompletedProcess[str]:
        (kwargs["config"].hermes_home / "state.db").write_text("", encoding="utf-8")
        kwargs["usage_file"].write_text(json.dumps({"api_calls": 1}), encoding="utf-8")
        return subprocess.CompletedProcess(args=["hermes"], returncode=0, stdout="done", stderr="")

    def fake_export(**kwargs: Any) -> subprocess.CompletedProcess[str]:
        raw = _session_jsonl(
            kwargs["workspace"],
            messages=[
                {"role": "user", "content": "Say hello."},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "function": {
                                "name": "run_shell",
                                "arguments": '{"command": "rm -rf /tmp/x"}',
                            },
                        }
                    ],
                },
                {"role": "assistant", "content": "done"},
            ],
        )
        return subprocess.CompletedProcess(args=["hermes"], returncode=0, stdout=raw, stderr="")

    monkeypatch.setattr(backend, "_run_hermes_subprocess", fake_run)
    monkeypatch.setattr(hermes_module, "_run_hermes_sessions_export", fake_export)
    context = _context(tmp_path)

    backend.initialize_run(context)
    result = backend.execute_task(task=_task(), context=context, attempt_run_id="run_001-1")

    assert result["status"] == "success"
    assert result["backend_metadata"]["transcript_source"] == "hermes_sessions_export"
    assert result["backend_metadata"]["transcript_extraction"]["session_id"] == "session-1"
    blocks = [
        block
        for entry in result["transcript"]
        for block in entry["message"].get("content", [])
        if isinstance(block, dict)
    ]
    assert any(
        block.get("type") == "toolCall" and block.get("name") == "run_shell" for block in blocks
    )


def test_hermes_backend_falls_back_when_export_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import benchmark.backends.hermes as hermes_module

    _configure_hermes_test_env(monkeypatch)
    monkeypatch.setattr(hermes_module.shutil, "which", lambda _: "/usr/bin/hermes")
    backend = HermesBackend()

    def fake_run(**kwargs: Any) -> subprocess.CompletedProcess[str]:
        (kwargs["config"].hermes_home / "state.db").write_text("", encoding="utf-8")
        kwargs["usage_file"].write_text(json.dumps({"api_calls": 1}), encoding="utf-8")
        return subprocess.CompletedProcess(args=["hermes"], returncode=0, stdout="done", stderr="")

    monkeypatch.setattr(backend, "_run_hermes_subprocess", fake_run)
    monkeypatch.setattr(
        hermes_module,
        "_run_hermes_sessions_export",
        lambda **kwargs: subprocess.CompletedProcess(
            args=["hermes"], returncode=2, stdout="", stderr="boom"
        ),
    )
    context = _context(tmp_path)

    backend.initialize_run(context)
    result = backend.execute_task(task=_task(), context=context, attempt_run_id="run_001-1")

    assert result["status"] == "success"
    assert (
        result["backend_metadata"]["transcript_source"]
        == "hermes_sessions_export_failed_fallback_stdout"
    )
    assert result["backend_metadata"]["transcript_extraction"]["fallback_reason"] == "failed"
    assert result["transcript"][-1]["message"]["content"] == [{"type": "text", "text": "done"}]
