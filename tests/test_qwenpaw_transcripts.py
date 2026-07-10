from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from benchmark.backends.qwenpaw import (  # noqa: E402
    _msg_to_transcript_entry,
    _raw_messages_to_transcript,
)
from lib_reward import (  # noqa: E402
    _check_dangerous_commands,
    _check_skill_invocation,
    _transcript_to_text,
)


def _entry(message: Any) -> dict[str, Any]:
    entry = _msg_to_transcript_entry(message)
    assert entry is not None
    return entry


class FakeMessage:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def to_dict(self) -> dict[str, Any]:
        return self.payload


def test_qwenpaw_message_normalizes_text_tool_calls_and_tool_results() -> None:
    transcript = [
        _entry({"role": "user", "content": "Read README.md"}),
        _entry(
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
            }
        ),
        _entry(
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "tool_name": "read_file",
                "content": "hello",
            }
        ),
        _entry({"role": "assistant", "content": "done"}),
    ]

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
    assert transcript[2]["message"]["content"][0] == {
        "type": "toolResult",
        "text": "hello",
        "tool_call_id": "call_1",
        "name": "read_file",
    }
    assert transcript[3]["message"]["content"] == [{"type": "text", "text": "done"}]


def test_qwenpaw_message_parses_json_string_tool_calls_and_raw_arguments() -> None:
    tool_calls = json.dumps(
        [
            {
                "call_id": "call_raw",
                "type": "function",
                "function": {"name": "run_shell", "arguments": "not-json"},
            }
        ]
    )

    entry = _entry({"role": "assistant", "content": [], "tool_calls": tool_calls})

    block = entry["message"]["content"][0]
    assert block["type"] == "toolCall"
    assert block["name"] == "run_shell"
    assert block["id"] == "call_raw"
    assert block["arguments"] == {"raw": "not-json"}


def test_qwenpaw_message_normalizes_function_call() -> None:
    entry = _entry(
        {
            "role": "assistant",
            "content": None,
            "function_call": {"name": "run_shell", "arguments": '{"command": "ls"}'},
        }
    )

    assert entry["message"]["content"] == [
        {"type": "toolCall", "name": "run_shell", "arguments": {"command": "ls"}}
    ]


def test_qwenpaw_message_normalizes_tool_use_content_block() -> None:
    entry = _entry(
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "read_file",
                    "input": {"path": "README.md"},
                }
            ],
        }
    )

    assert entry["message"]["content"] == [
        {
            "type": "toolCall",
            "name": "read_file",
            "arguments": {"path": "README.md"},
            "id": "toolu_1",
        }
    ]


def test_qwenpaw_message_normalizes_service_plugin_calls_and_outputs() -> None:
    transcript = [
        _entry(
            {
                "type": "plugin_call",
                "role": "assistant",
                "content": [
                    {
                        "type": "data",
                        "data": {
                            "call_id": "call_1",
                            "name": "read_file",
                            "arguments": '{"file_path": "README.md"}',
                        },
                    }
                ],
            }
        ),
        _entry(
            {
                "type": "plugin_call_output",
                "role": "system",
                "content": [
                    {
                        "type": "data",
                        "data": {
                            "call_id": "call_1",
                            "name": "read_file",
                            "output": "hello",
                        },
                    }
                ],
            }
        ),
    ]

    assert transcript[0]["message"] == {
        "role": "assistant",
        "content": [
            {
                "type": "toolCall",
                "name": "read_file",
                "arguments": {"file_path": "README.md"},
                "id": "call_1",
            }
        ],
    }
    assert transcript[1]["message"] == {
        "role": "toolResult",
        "content": [
            {
                "type": "toolResult",
                "text": "hello",
                "tool_call_id": "call_1",
                "name": "read_file",
            }
        ],
    }


def test_qwenpaw_message_supports_to_dict_objects() -> None:
    entry = _entry(FakeMessage({"role": "assistant", "content": "done"}))

    assert entry["message"]["content"] == [{"type": "text", "text": "done"}]


def test_qwenpaw_raw_messages_to_transcript_normalizes_service_messages() -> None:
    transcript = _raw_messages_to_transcript(
        [
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
        ]
    )

    assert transcript[0]["message"]["role"] == "user"
    assert transcript[1]["message"]["content"][0]["type"] == "toolCall"
    assert transcript[1]["message"]["content"][0]["name"] == "read_file"


def test_qwenpaw_raw_messages_to_transcript_accepts_tuple_like_entries() -> None:
    transcript = _raw_messages_to_transcript(
        [
            [
                {
                    "role": "assistant",
                    "content": None,
                    "function_call": {
                        "name": "run_shell",
                        "arguments": '{"command": "pwd"}',
                    },
                },
                {"metadata": True},
            ]
        ]
    )

    assert transcript[0]["message"]["content"][0] == {
        "type": "toolCall",
        "name": "run_shell",
        "arguments": {"command": "pwd"},
    }


def test_qwenpaw_tool_call_arguments_are_reward_compatible(tmp_path: Path) -> None:
    transcript = [
        _entry(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_shell",
                        "function": {
                            "name": "run_shell",
                            "arguments": '{"command": "rm -rf /tmp/x"}',
                        },
                    }
                ],
            }
        )
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
