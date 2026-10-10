"""Public-release redaction and leak scanning helpers for ActBench artifacts.

The release pipeline writes public copies of raw evidence.  This module provides
small, deterministic redaction helpers plus a conservative scanner that reports
potential leaks without printing matched secret values.
"""

from __future__ import annotations

import ast
import copy
import getpass
import hashlib
from functools import lru_cache
import json
import os
import re
import shutil
import socket
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

try:  # pragma: no cover - import guard for standalone use
    from lib_mock_secrets import SECRET_PLACEHOLDER_RE
except Exception:  # pragma: no cover
    SECRET_PLACEHOLDER_RE = re.compile(r"\{\{CLAWEVAL_SECRET:[^}]+\}\}")


_TEXT_SUFFIXES = {
    ".cfg",
    ".conf",
    ".csv",
    ".env",
    ".ini",
    ".json",
    ".jsonl",
    ".log",
    ".md",
    ".py",
    ".sh",
    ".text",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}

_HOME_PATH_RE = re.compile(
    r"(?:/(?:data/)?home/+[A-Za-z0-9._-]+|/Users/[A-Za-z0-9._-]+|/mnt/[A-Za-z]/Users/[A-Za-z0-9._-]+)"
    r"(?:/[^\s\"'<>:]*)?"
    r"|[A-Za-z]:\\+Users\\+[A-Za-z0-9._-]+(?:\\+[^\s\"'<>;]*)?"
)
_LOCAL_IDENTITY_ENV_RE = re.compile(
    r"(?P<prefix>(?:(?<![A-Za-z0-9_])|(?<=\\n)|(?<=\\r))"
    r"(?P<identity_key>USER|LOGNAME|USERNAME|HOSTNAME)[ \t]*=[ \t]*)"
    r"(?P<identity_value>[^\s\\\r\n\"'`,;}>\]]+)"
)
_JSON_LOCAL_IDENTITY_FIELD_RE = re.compile(
    r"(?P<prefix>[\"'](?P<identity_key>USER|LOGNAME|USERNAME|HOSTNAME)[\"'][ \t]*:[ \t]*[\"'])"
    r"(?P<identity_value>[^\\\r\n\"']+)(?P<suffix>[\"'])"
)
_SSH_IDENTITY_ENV_RE = re.compile(
    r"(?P<prefix>(?:(?<![A-Za-z0-9_])|(?<=\\n)|(?<=\\r))"
    r"(?P<identity_key>SSH_CLIENT|SSH_CONNECTION)[ \t]*=[ \t]*)"
    r"(?P<identity_value>[^\\\r\n\"'`,;}\]]+)"
)
_JSON_SSH_IDENTITY_FIELD_RE = re.compile(
    r"(?P<prefix>[\"'](?P<identity_key>SSH_CLIENT|SSH_CONNECTION)[\"'][ \t]*:[ \t]*[\"'])"
    r"(?P<identity_value>[^\\\r\n\"']+)(?P<suffix>[\"'])"
)
_SAFE_LOCAL_IDENTITY_VALUES = {"$USER", "${USER}", "$HOSTNAME", "${HOSTNAME}"}
_LOCAL_USERNAME_PLACEHOLDER = "$USER"
_LOCAL_HOSTNAME_PLACEHOLDER = "$HOSTNAME"
_LOCAL_IDENTITY_IGNORED_USERNAMES = {"root", "runner", "unknown"}
_LOCAL_IDENTITY_IGNORED_HOSTNAMES = {"localhost", "localhost.localdomain", "unknown"}
_LS_LONG_LINE_RE = re.compile(
    r"(?m)^([bcdlps-][rwxXsStT-]{9}[+.@]?\s+\d+\s+)"
    r"([A-Za-z0-9._-]+)(\s+)([A-Za-z0-9._-]+)(\s+)"
)
_MOCK_FAKE_API_KEY_RE = re.compile(r"\bsk-claw-[A-Za-z0-9._-]+\b")
_TRUNCATED_API_KEY_RE = re.compile(r"\b(?:sk|ak|pk|rk|or)-[A-Za-z0-9._-]{1,16}…[A-Za-z0-9._-]{2,16}\b")
_GENERIC_TRUNCATED_SECRET_RE = re.compile(r"\b[A-Za-z0-9._-]{2,32}…[A-Za-z0-9._-]{2,32}\b")
_CODE_TRUNCATED_SECRET_RE = re.compile(r"[A-Za-z0-9_$().\\/-]{1,32}…[A-Za-z0-9_$().\\/-]{1,32}")
_TRUNCATED_SHELL_VARIABLE_RE = re.compile(r"\$[A-Za-z0-9_]{1,32}…[A-Za-z0-9_]{1,32}")
_REDACTED_STAR_PLACEHOLDER_RE = re.compile(r"\*+")
_BACKSLASH_ESCAPE_RUN_RE = re.compile(r"\\+")
_ESCAPED_OR_LITERAL_LINE_BREAK_RE = re.compile(r"(?:\\+r\\+n|\\+[rn]|\r\n|\n|\r)+")
_ESCAPED_OR_LITERAL_LINE_BREAK_PREFIX_RE = re.compile(r"\A(?:\\+r\\+n|\\+[rn]|\r\n|\n|\r)")
_TRAILING_PUBLIC_PLACEHOLDER_PUNCTUATION = "\\.,:;!?)]}`'\""
_NESTED_SECRET_ASSIGNMENT_SEGMENT_RE = re.compile(
    r"(?i)\A(?:[-*+]\s+)?(?:`)?(?:"
    r"[A-Z0-9_-]*(?:api[_-]?key|auth[_-]?token|access[_-]?token|refresh[_-]?token|secret|password|passwd)"
    r"|token|[A-Z0-9_-]+[_-]token)[A-Z0-9_-]*(?:`)?"
    r"[\w\- \t\"']{0,20}[:=][ \t]*(?:`)?(?P<secret_value>[^\\\r\n\"'`,;>}\]]+)(?:`)?\Z"
)
_NUMBERED_SECRET_SECTION_KEY_RE = re.compile(r"(?i)\ASECRET[-_ ]?\d+\Z")
_NATURAL_LANGUAGE_SECRET_SECTION_KEYS = {"secret_adjacent", "secret_handling", "secret_ish", "secret_like", "secrets"}
_NATURAL_LANGUAGE_TOKEN_SECTION_KEYS = {"token", "tokens"}
_NATURAL_LANGUAGE_SECRET_FOLLOWING_HEADINGS = {"approved", "guidance"}
_MARKDOWN_SECTION_SEGMENT_RE = re.compile(r"(?:[-=]{3,}[A-Za-z0-9_-]*|#{1,6}(?:\s+[A-Za-z][A-Za-z .:—-]{0,60})?)")
_PUBLIC_OUTPUT_BANNER_RE = re.compile(r"\A={2,}[A-Za-z0-9_. -]{1,80}={2,}\Z")
_MARKDOWN_SECTION_PREFIX_RE = re.compile(r"\A(?:#{1,6}\s*|[-*+]\s*)+")
_SHELL_VARIABLE_REFERENCE_RE = re.compile(r"\$[A-Z_][A-Z0-9_]{1,80}")
_SHELL_VARIABLE_PATH_RE = re.compile(r"\$[A-Z_][A-Z0-9_]{1,80}(?:/[A-Za-z0-9._:@%+=-]+)+")
_SOURCE_LOCATION_SEGMENT_RE = re.compile(
    r"(?:\.?/)?[A-Za-z0-9._/-]+:\d+:(?:[A-Za-z>][A-Za-z0-9_ .:>/-]{0,120})?"
)
_SHELL_SOURCE_LOCATION_SEGMENT_RE = re.compile(
    r"\A\$[A-Z_][A-Z0-9_]*(?:/[A-Za-z0-9._:@%+=-]+)*:\d+:[^\r\n]{0,240}\Z"
)
_TERMINAL_STYLE_PREFIX_RE = re.compile(r"\A(?:\$[A-Za-z_]+(?::[A-Za-z0-9_]+)*:)+")
_SOURCE_LOCATION_PREFIX_RE = re.compile(r"\A(?:(?:\.?/)?[A-Za-z0-9._/-]+:\d+:)+")
_CODE_FRAGMENT_SECRET_VALUE_RE = re.compile(r"\A(?:\)|,|\]|\}|\.|[A-Za-z_][A-Za-z0-9_.]*(?:\(|\[|\{))")
_LINE_MARKER_SEGMENT_RE = re.compile(r"\A(?:\d+[.:]?|-[A-Za-z0-9-]{3,40}(?:\s+[A-Za-z][A-Za-z .:-]{0,80})?)\Z")
_REDACTED_NOTE_SEGMENT_RE = re.compile(r"(?i)\A\((?:redacted|command)(?:\s+[A-Za-z]+){0,8}\)?\Z")
_BENIGN_CONTEXT_ASSIGNMENT_RE = re.compile(r"\A[A-Z][A-Z0-9_]{1,40}=[^\r\n]*\Z")
_BENIGN_FLAG_ASSIGNMENT_RE = re.compile(r"(?i)\A[A-Z_][A-Z0-9_]{1,80}=(?:0|1|true|false)\Z")
_BENIGN_METADATA_ASSIGNMENT_RE = re.compile(
    r"(?i)\A[A-Z0-9_]*(?:present|configured|source|env|env_var)[A-Z0-9_]*="
    r"(?:0|1|true|false|[A-Z][A-Z0-9_]{2,}|/[^\r\n]*)\Z"
)
_BENIGN_SECTION_ASSIGNMENT_RE = re.compile(
    r"(?i)\A[a-z_][a-z0-9_ -]{0,40}=(?:0|1|true|false|yes|no|none|null)\Z"
)
_BENIGN_COUNT_ASSIGNMENT_RE = re.compile(r"(?i)\A(?:total|count|matches|results|items|rows)=\d{1,6}\Z")
_BENIGN_PUBLIC_CONTEXT_ASSIGNMENT_RE = re.compile(
    r"(?i)\A[_a-z][a-z0-9_]{0,40}="
    r"(?:"
    r"\$[A-Z_][A-Z0-9_]{1,80}(?:/[A-Za-z0-9._:@%+=-]+)*"
    r"|(?:https?|socks5)://(?:127\.0\.0\.1|localhost)(?::\d{2,5})?(?:/[A-Za-z0-9._~:/?#[\]@!$&'()*+,;=%-]*)?"
    r"|[A-Za-z_][A-Za-z0-9_.]*(?:\(|\[|\{)?"
    r")\Z"
)
_BENIGN_PUBLIC_FILE_LABEL_RE = re.compile(
    r"\A(?:"
    r"(?:\.{1,2}/)?(?:\.[A-Za-z0-9_-]{1,32}|[A-Za-z0-9_-]{1,64}\.[A-Za-z0-9_-]{1,12})"
    r"|__pycache__"
    r")\Z"
)
_NON_SECRET_ASSIGNMENT_KEYS = {"tokenize"}
_SEARCH_OUTPUT_SECRET_HEADING_RE = re.compile(
    r"(?i)\b[A-Z0-9_-]*(?:api[_-]?key|auth[_-]?token|access[_-]?token|refresh[_-]?token|secret|password|passwd|token)"
    r"[A-Z0-9_-]*\s+(?:anywhere|in\s+workspace|in\s+(?:any\s+)?files?)\s*=+"
)
_NATURAL_LANGUAGE_SECTION_SEGMENT_RE = re.compile(r"[A-Za-z][A-Za-z .:-]{0,40}")
_NATURAL_LANGUAGE_HEADING_SEGMENT_RE = re.compile(r"[A-Za-z][A-Za-z0-9 .,:—_-]{0,80}")
_PRIVATE_KEY_BLOCK_RE = re.compile(
    r"-----BEGIN (?P<label>[A-Z0-9 ]*PRIVATE KEY)-----.*?-----END (?P=label)-----",
    re.DOTALL,
)
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(?P<secret_key>(?!REDACTED_)(?:"
    r"[A-Z0-9_-]*(?:api[_-]?key|auth[_-]?token|access[_-]?token|refresh[_-]?token|secret|password|passwd)"
    r"|token|[A-Z0-9_-]+[_-]token)[A-Z0-9_-]*)"
    r"[\w\- \t\"']{0,20}[:=][ \t]*"
    r"(?:"
    r"\"(?P<secret_value_dq>\{\{CLAWEVAL_SECRET:[A-Z][A-Z0-9_]{2,}\}\}|[^\r\n\"]{12,})\""
    r"|'(?P<secret_value_sq>\{\{CLAWEVAL_SECRET:[A-Z][A-Z0-9_]{2,}\}\}|[^\r\n']{12,})'"
    r"|(?P<secret_value>\{\{CLAWEVAL_SECRET:[A-Z][A-Z0-9_]{2,}\}\}|[^\s\"'`<>,;}\]]{12,})"
    r")"
)
_MULTILINE_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(?P<secret_key>(?!REDACTED_)(?:"
    r"[A-Z0-9_-]*(?:api[_-]?key|auth[_-]?token|access[_-]?token|refresh[_-]?token|secret|password|passwd)"
    r"|token|[A-Z0-9_-]+[_-]token)[A-Z0-9_-]*)"
    r"[\w\- \t\"']{0,20}[:=][ \t]*"
    r"(?P<secret_value>(?:\r\n|\n|\r)+[ \t]*(?:`)?[^\s\"'`<>,;}\]]{12,}(?:`)?)"
)
_PRIVATE_PROVIDER_URL_RE = re.compile(
    r"https?://(?:[^/\s\"'\\},]*\.)?(?:zjuicsr\.cn|tokenhub[^/\s\"'\\},]*)(?:/[^\s\"'\\},]*)?"
)
_PRIVATE_PROVIDER_URL_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(?P<secret_key>[A-Z0-9_]*(?:base[_-]?url|api[_-]?url|endpoint|router[_-]?url)[A-Z0-9_-]*)"
    r"[\w\- \t\"']{0,20}[:=][ \t]*[\"']?"
    r"(?P<secret_value>https?://(?:[^/\s\"'\\},]*\.)?(?:zjuicsr\.cn|tokenhub[^/\s\"'\\},]*)(?:/[^\s\"'\\},]*)?)"
)

_ASSIGNMENT_SECRET_KINDS = {"secret_assignment", "private_provider_url_assignment"}
_PROVIDER_SECRET_KEY_MARKERS = (
    "anthropic",
    "deepseek",
    "openrouter",
    "taisure",
    "zjuicsr",
    "minimax",
    "moonshot",
    "tencent",
    "openai",
    "github",
    "huggingface",
    "hf_",
    "aws",
    "gcp",
    "google",
    "azure",
)
_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private_key", re.compile(r"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")),
    (
        "jwt",
        re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    ),
    ("bearer_token", re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{16,}\b")),
    ("api_key", re.compile(r"\b(?:sk|ak|pk|rk|or)-[A-Za-z0-9][A-Za-z0-9._-]{15,}\b")),
    ("secret_assignment", _MULTILINE_SECRET_ASSIGNMENT_RE),
    ("secret_assignment", _SECRET_ASSIGNMENT_RE),
    ("private_provider_url_assignment", _PRIVATE_PROVIDER_URL_ASSIGNMENT_RE),
    ("private_provider_url", _PRIVATE_PROVIDER_URL_RE),
    ("home_path", _HOME_PATH_RE),
)

_TMP_PATH_RE = re.compile(r"/tmp/(?:claweval|actbench|tmp)[A-Za-z0-9._/-]*")
_OMITTED_INTERNAL_ARTIFACT_NAMES = {"history.db"}
_INTERNAL_HISTORY_SCHEMA_MARKERS = (b"conversation_history", b"tool_input", b"tool_state", b"conversation_history_fts")
_OMITTED_INTERNAL_ARTIFACT_TEXT = (
    "ActBench public release note: this internal agent history database was omitted because it may contain "
    "local command history, environment variables, or machine-specific state. The public trajectory.json and "
    "other workspace files remain available for replay and inspection.\n"
)
_OMITTED_SYMLINK_TEXT = (
    "ActBench public release note: this symbolic link was omitted because public release copies do not follow "
    "links outside the captured workspace tree.\n"
)
_OMITTED_SYMLINK_DIRECTORY_NOTE = ".actbench_omitted_symlink.txt"


@dataclass(frozen=True)
class RedactionHit:
    """One potential public-release leak."""

    path: str
    kind: str
    line: int | None = None
    fingerprint: str = ""


@dataclass
class RedactionScanResult:
    """Aggregate result from scanning one or more release roots."""

    scanned_files: int = 0
    skipped_files: int = 0
    hits: list[RedactionHit] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.hits and self.skipped_files == 0

    def summary(self) -> dict[str, Any]:
        by_kind: dict[str, int] = {}
        for hit in self.hits:
            by_kind[hit.kind] = by_kind.get(hit.kind, 0) + 1
        return {
            "ok": self.ok,
            "scanned_files": self.scanned_files,
            "skipped_files": self.skipped_files,
            "hit_count": len(self.hits),
            "hits_by_kind": dict(sorted(by_kind.items())),
            "hits": [hit.__dict__ for hit in self.hits],
        }


class RedactionError(ValueError):
    """Raised when release redaction or scanning fails."""


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:16]


def _local_username_values() -> tuple[str, ...]:
    candidates = {os.environ.get("USER", ""), os.environ.get("LOGNAME", ""), os.environ.get("USERNAME", "")}
    try:
        candidates.add(getpass.getuser())
    except (KeyError, OSError):
        pass
    return tuple(
        sorted(
            {
                value.strip()
                for value in candidates
                if 2 <= len(value.strip()) <= 128
                and value.strip().lower() not in _LOCAL_IDENTITY_IGNORED_USERNAMES
            },
            key=lambda value: (-len(value), value),
        )
    )


def _local_hostname_values() -> tuple[str, ...]:
    candidates = {os.environ.get("HOSTNAME", "")}
    try:
        candidates.add(socket.gethostname())
    except OSError:
        pass
    return tuple(
        sorted(
            {
                value.strip()
                for value in candidates
                if 2 <= len(value.strip()) <= 255
                and value.strip().lower() not in _LOCAL_IDENTITY_IGNORED_HOSTNAMES
            },
            key=lambda value: (-len(value), value),
        )
    )


def _identity_token_pattern(values: Sequence[str], *, ignore_case: bool = False) -> re.Pattern[str] | None:
    if not values:
        return None
    alternatives = "|".join(re.escape(value) for value in values)
    flags = re.IGNORECASE if ignore_case else 0
    return re.compile(
        rf"(?:(?<![A-Za-z0-9_])|(?<=\\n)|(?<=\\r))(?:{alternatives})(?![A-Za-z0-9_])",
        flags,
    )


@lru_cache(maxsize=16)
def _compile_local_identity_patterns(
    hostnames: tuple[str, ...],
    usernames: tuple[str, ...],
) -> tuple[tuple[str, re.Pattern[str]], ...]:
    patterns: list[tuple[str, re.Pattern[str]]] = []
    hostname_pattern = _identity_token_pattern(hostnames, ignore_case=True)
    username_pattern = _identity_token_pattern(usernames)
    if hostname_pattern is not None:
        patterns.append(("local_hostname", hostname_pattern))
    if username_pattern is not None:
        patterns.append(("local_username", username_pattern))
    return tuple(patterns)


def _local_identity_patterns() -> tuple[tuple[str, re.Pattern[str]], ...]:
    return _compile_local_identity_patterns(_local_hostname_values(), _local_username_values())


def _identity_placeholder(key: str) -> str:
    return _LOCAL_HOSTNAME_PLACEHOLDER if key.upper() == "HOSTNAME" else _LOCAL_USERNAME_PLACEHOLDER


def _is_safe_local_identity_value(value: str) -> bool:
    cleaned = value.strip()
    return cleaned in _SAFE_LOCAL_IDENTITY_VALUES or cleaned.startswith("<REDACTED_")


def _redact_local_identity_assignment(match: re.Match[str]) -> str:
    suffix = match.groupdict().get("suffix") or ""
    return f"{match.group('prefix')}{_identity_placeholder(match.group('identity_key'))}{suffix}"


def _redact_ssh_identity_assignment(match: re.Match[str]) -> str:
    suffix = match.groupdict().get("suffix") or ""
    key = match.group("identity_key").upper()
    value = match.group("identity_value")
    if _is_safe_local_identity_value(value):
        return match.group(0)
    return f"{match.group('prefix')}<REDACTED_{key}:{_fingerprint(value)}>{suffix}"


def _execution_identity_hits(
    text: str,
    *,
    path: str,
    line_number: int | None,
    kind_prefix: str = "",
    identity_patterns: Sequence[tuple[str, re.Pattern[str]]] | None = None,
) -> list[RedactionHit]:
    hits: list[RedactionHit] = []
    covered_spans: list[tuple[int, int]] = []
    structural_patterns = (
        ("local_identity_assignment", _LOCAL_IDENTITY_ENV_RE),
        ("local_identity_assignment", _JSON_LOCAL_IDENTITY_FIELD_RE),
        ("local_ssh_assignment", _SSH_IDENTITY_ENV_RE),
        ("local_ssh_assignment", _JSON_SSH_IDENTITY_FIELD_RE),
    )
    for kind, pattern in structural_patterns:
        for match in pattern.finditer(text):
            if _is_safe_local_identity_value(match.group("identity_value")):
                continue
            raw = match.group(0)
            covered_spans.append(match.span())
            hits.append(
                RedactionHit(
                    path=path,
                    kind=f"{kind_prefix}{kind}",
                    line=line_number,
                    fingerprint=_fingerprint(f"{kind}:{raw}"),
                )
            )
    patterns = tuple(identity_patterns) if identity_patterns is not None else _local_identity_patterns()
    for kind, pattern in patterns:
        for match in pattern.finditer(text):
            if any(start <= match.start() and match.end() <= end for start, end in covered_spans):
                continue
            raw = match.group(0)
            covered_spans.append(match.span())
            hits.append(
                RedactionHit(
                    path=path,
                    kind=f"{kind_prefix}{kind}",
                    line=line_number,
                    fingerprint=_fingerprint(f"{kind}:{raw}"),
                )
            )
    return hits


_ENV_VAR_NAME_RE = re.compile(r"[A-Z][A-Z0-9_]{2,}")
_REDACTED_VALUE_RE = re.compile(r"<REDACTED_[A-Z0-9_]+:[0-9a-f]{16}>")


def _matched_secret_value(match: re.Match[str]) -> str:
    for group_name in ("secret_value", "secret_value_dq", "secret_value_sq"):
        if group_name in match.re.groupindex:
            value = match.group(group_name)
            if value is not None:
                return value
    if match.groups():
        return match.group(1)
    return match.group(0)


def _matched_secret_key(match: re.Match[str]) -> str:
    group_name = "secret_key"
    if group_name in match.re.groupindex:
        return match.group(group_name)
    whole = match.group(0)
    return re.split(r"[:=]", whole, maxsplit=1)[0].strip(" \t\"'")


def _is_metadata_reference_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")
    return normalized.endswith(("_source", "_env", "_env_var", "_present"))


def _is_private_provider_secret_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")
    return any(marker in normalized for marker in _PROVIDER_SECRET_KEY_MARKERS)


def _public_placeholder_value(value: str) -> str:
    cleaned = value.strip().strip(_TRAILING_PUBLIC_PLACEHOLDER_PUNCTUATION)
    if "…" in cleaned:
        cleaned = cleaned.rstrip("=")
    return cleaned


def _is_safe_fake_or_truncated_api_key(value: str) -> bool:
    value = _public_placeholder_value(value)
    return bool(
        _MOCK_FAKE_API_KEY_RE.fullmatch(value)
        or _TRUNCATED_API_KEY_RE.fullmatch(value)
        or _GENERIC_TRUNCATED_SECRET_RE.fullmatch(value)
        or _CODE_TRUNCATED_SECRET_RE.fullmatch(value)
        or _TRUNCATED_SHELL_VARIABLE_RE.fullmatch(value)
        or _REDACTED_STAR_PLACEHOLDER_RE.fullmatch(value)
    )


def _strip_public_output_prefixes(value: str) -> str:
    current = value.strip()
    while True:
        stripped = _TERMINAL_STYLE_PREFIX_RE.sub("", current, count=1)
        stripped = _SOURCE_LOCATION_PREFIX_RE.sub("", stripped, count=1)
        if stripped == current:
            return current.strip().strip("\\")
        current = stripped.strip()


def _is_safe_public_assignment_value(value: str) -> bool:
    cleaned = _public_placeholder_value(value)
    return bool(
        _is_safe_fake_or_truncated_api_key(value)
        or _SHELL_VARIABLE_REFERENCE_RE.fullmatch(cleaned)
        or _SHELL_VARIABLE_PATH_RE.fullmatch(cleaned)
    )


def _is_benign_public_payload_segment(part: str, *, saw_secret_placeholder: bool) -> bool:
    if not saw_secret_placeholder:
        return False
    if set(part) <= {"\\", "-", "*", "+", "{", "}", "[", "]", "(", ")", ":", ".", ",", "=", "\"", "'"}:
        return True
    nested = _NESTED_SECRET_ASSIGNMENT_SEGMENT_RE.fullmatch(part)
    if nested:
        nested_value = nested.group("secret_value")
        return _is_safe_public_assignment_value(nested_value) or _BENIGN_METADATA_ASSIGNMENT_RE.fullmatch(part) is not None
    if _LINE_MARKER_SEGMENT_RE.fullmatch(part):
        return True
    if _SOURCE_LOCATION_SEGMENT_RE.fullmatch(part) or _SHELL_SOURCE_LOCATION_SEGMENT_RE.fullmatch(part):
        return True
    if _REDACTED_NOTE_SEGMENT_RE.fullmatch(part):
        return True
    if _MARKDOWN_SECTION_SEGMENT_RE.fullmatch(part) or _PUBLIC_OUTPUT_BANNER_RE.fullmatch(part):
        return True
    if _SHELL_VARIABLE_REFERENCE_RE.fullmatch(part) or _SHELL_VARIABLE_PATH_RE.fullmatch(part):
        return True
    if _BENIGN_PUBLIC_CONTEXT_ASSIGNMENT_RE.fullmatch(part) or _BENIGN_PUBLIC_FILE_LABEL_RE.fullmatch(part):
        return True
    if _is_natural_section_part(part, allow_lowercase=True):
        return True
    if _BENIGN_CONTEXT_ASSIGNMENT_RE.fullmatch(part):
        return True
    if _BENIGN_FLAG_ASSIGNMENT_RE.fullmatch(part):
        return True
    if _BENIGN_METADATA_ASSIGNMENT_RE.fullmatch(part):
        return True
    if _CODE_FRAGMENT_SECRET_VALUE_RE.match(part):
        return True
    return False


def _is_mock_fake_api_key_payload(value: str) -> bool:
    value = value.strip().rstrip("\\")
    if _is_safe_fake_or_truncated_api_key(value):
        return True
    if _CODE_FRAGMENT_SECRET_VALUE_RE.match(value):
        return True
    parts = _ESCAPED_OR_LITERAL_LINE_BREAK_RE.split(value)
    if len(parts) <= 1:
        return False
    saw_value = False
    for raw_part in parts:
        part = _strip_public_output_prefixes(raw_part)
        if not part:
            continue
        if _is_safe_fake_or_truncated_api_key(part):
            saw_value = True
            continue
        if set(part) <= {"\\", "-", "*", "+"}:
            continue
        nested = _NESTED_SECRET_ASSIGNMENT_SEGMENT_RE.fullmatch(part)
        if nested and _is_safe_public_assignment_value(nested.group("secret_value")):
            saw_value = True
            continue
        if _is_benign_public_payload_segment(part, saw_secret_placeholder=saw_value):
            continue
        return False
    return saw_value


def _starts_with_escaped_or_literal_line_break(value: str) -> bool:
    return bool(_ESCAPED_OR_LITERAL_LINE_BREAK_PREFIX_RE.match(value))


def _normalize_section_heading_part(part: str) -> str:
    text = part.strip().strip("\\").strip()
    text = _MARKDOWN_SECTION_PREFIX_RE.sub("", text).strip()
    return text.strip("`*_").strip(_TRAILING_PUBLIC_PLACEHOLDER_PUNCTUATION + "(").strip()


def _is_secret_like_unbroken_text(text: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9._-]{20,}", text.strip()))


def _is_natural_section_part(part: str, *, allow_lowercase: bool) -> bool:
    raw = part.strip().strip("\\").strip()
    if not raw:
        return False
    if _MARKDOWN_SECTION_SEGMENT_RE.fullmatch(raw):
        return True
    text = _normalize_section_heading_part(raw)
    if not text or _is_secret_like_unbroken_text(text):
        return False
    if _LINE_MARKER_SEGMENT_RE.fullmatch(text):
        return True
    if not allow_lowercase and not text[0].isupper():
        return False
    return bool(
        _NATURAL_LANGUAGE_SECTION_SEGMENT_RE.fullmatch(text)
        or _NATURAL_LANGUAGE_HEADING_SEGMENT_RE.fullmatch(text)
    )


def _is_natural_language_sensitive_part(part: str, *, allow_lowercase: bool) -> bool:
    raw = part.strip().strip("\\").strip()
    if not raw:
        return False
    if set(raw) <= {"\\", "-", "*", "+", "{", "}", "[", "]", "(", ")", ":", ".", ",", "=", "\"", "'", "#"}:
        return True
    if _PUBLIC_OUTPUT_BANNER_RE.fullmatch(raw):
        return True
    if _SOURCE_LOCATION_SEGMENT_RE.fullmatch(raw) or _SHELL_SOURCE_LOCATION_SEGMENT_RE.fullmatch(raw):
        return True
    if _BENIGN_PUBLIC_FILE_LABEL_RE.fullmatch(raw):
        return True
    normalized = _normalize_section_heading_part(raw)
    if _BENIGN_SECTION_ASSIGNMENT_RE.fullmatch(normalized) or _BENIGN_COUNT_ASSIGNMENT_RE.fullmatch(normalized):
        return True
    return _is_natural_section_part(part, allow_lowercase=allow_lowercase)


def _is_numbered_secret_section(key: str, value: str) -> bool:
    if not _NUMBERED_SECRET_SECTION_KEY_RE.fullmatch(key):
        return False
    if _starts_with_escaped_or_literal_line_break(value):
        parts = [part.strip().strip("\\") for part in _ESCAPED_OR_LITERAL_LINE_BREAK_RE.split(value)]
        meaningful = [part for part in parts if part and not set(part) <= {"\\", "-", "*", "+"}]
        return not meaningful or all(_is_natural_section_part(part, allow_lowercase=True) for part in meaningful)
    parts = [part.strip().strip("\\") for part in _ESCAPED_OR_LITERAL_LINE_BREAK_RE.split(value)]
    if len(parts) <= 1:
        return False
    meaningful = [part for part in parts if part and not set(part) <= {"\\", "-", "*", "+"}]
    return bool(meaningful) and all(_is_natural_section_part(part, allow_lowercase=True) for part in meaningful)


def _is_natural_language_secret_section(key: str, value: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")
    natural_keys = {*_NATURAL_LANGUAGE_SECRET_SECTION_KEYS, *_NATURAL_LANGUAGE_TOKEN_SECTION_KEYS, "secret"}
    if normalized.startswith("n") and normalized[1:] in natural_keys:
        normalized = normalized[1:]
    if normalized not in natural_keys:
        return False
    parts = [part.strip() for part in _ESCAPED_OR_LITERAL_LINE_BREAK_RE.split(value)]
    if len(parts) <= 1:
        return False
    meaningful = [part.strip("\\") for part in parts if part and not set(part) <= {"\\", "-", "*", "+"}]
    if not meaningful:
        return False
    if normalized == "secret" and len(meaningful) == 1:
        if meaningful[0].lower().rstrip(":") in _NATURAL_LANGUAGE_SECRET_FOLLOWING_HEADINGS:
            return True
        return _is_natural_language_sensitive_part(meaningful[0], allow_lowercase=False)
    return all(_is_natural_language_sensitive_part(part, allow_lowercase=True) for part in meaningful)


def _segment_has_unsafe_nested_secret(part: str) -> bool:
    for kind, pattern in _SECRET_PATTERNS:
        if kind == "home_path":
            continue
        for nested in pattern.finditer(part):
            if _safe_secret_match(kind, nested):
                continue
            return True
    return False


def _is_reference_only_multiline_value(key: str, value: str) -> bool:
    if not _starts_with_escaped_or_literal_line_break(value):
        return False
    normalized_key = re.sub(r"[^A-Z0-9]+", "_", key.upper()).strip("_")
    parts = [part.strip().strip("\\").strip() for part in _ESCAPED_OR_LITERAL_LINE_BREAK_RE.split(value)]
    meaningful = [part for part in parts if part and not set(part) <= {"\\", "-", "*", "+", ">"}]
    if not meaningful:
        return False
    for part in meaningful:
        if _segment_has_unsafe_nested_secret(part):
            return False
        if set(part) <= {"\\", "-", "*", "+", "{", "}", "[", "]", "(", ")", ":", ".", ",", "=", "\"", "'", "#", ">"}:
            continue
        if _ENV_VAR_NAME_RE.fullmatch(part) and part == normalized_key:
            continue
        if _SOURCE_LOCATION_SEGMENT_RE.fullmatch(part) or _SHELL_SOURCE_LOCATION_SEGMENT_RE.fullmatch(part):
            continue
        if _PUBLIC_OUTPUT_BANNER_RE.fullmatch(part) or _BENIGN_PUBLIC_FILE_LABEL_RE.fullmatch(part):
            continue
        return False
    return True


def _secret_match_prefix(match: re.Match[str]) -> str:
    value = _matched_secret_value(match)
    whole = match.group(0)
    return whole[: -len(value)] if value and whole.endswith(value) else whole


def _normalized_secret_assignment_key(key: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")
    escaped_newline_keys = {
        "api_key",
        "apikey",
        "auth_token",
        "access_token",
        "refresh_token",
        "secret",
        "password",
        "passwd",
        "token",
        "tokens",
    }
    if normalized.startswith("n") and normalized[1:] in escaped_newline_keys:
        normalized = normalized[1:]
    return normalized


def _json_escape_compact(text: str) -> str:
    return re.sub(r"\\+", "", text.strip().strip("\"'`"))


def _is_code_condition_secret_key_reference(match: re.Match[str]) -> bool:
    prefix = _secret_match_prefix(match)
    recent = match.string[max(0, match.start() - 120) : match.start()] + prefix
    compact = _json_escape_compact(recent)
    return bool(
        re.search(r"[\"']?\s+(?:not\s+)?in\s+[A-Za-z_][A-Za-z0-9_]*\s*:\s*\Z", compact)
        or re.search(r"\b(?:if|while)\s+(?:not\s+)?[A-Za-z_][A-Za-z0-9_]*\s*:\s*\Z", compact)
    )


def _is_code_fragment_secret_assignment(match: re.Match[str]) -> bool:
    value = _matched_secret_value(match)
    compact = _json_escape_compact(value)
    if _CODE_FRAGMENT_SECRET_VALUE_RE.match(compact):
        return True
    lookahead = _json_escape_compact(value + match.string[match.end() : match.end() + 300])
    if compact.lower() == "nonenwith":
        lower_lookahead = lookahead.lower()
        opens_env = "with open('.env')" in lower_lookahead or 'with open(".env")' in lower_lookahead
        extracts_line_value = ".split(" in lower_lookahead or "line.s…lit(" in lower_lookahead
        return opens_env and "line.startswith(" in lower_lookahead and extracts_line_value
    return False


def _is_natural_encoded_token_reference(match: re.Match[str]) -> bool:
    key = _normalized_secret_assignment_key(_matched_secret_key(match))
    if key not in {"token", "tokens"}:
        return False
    prefix = _secret_match_prefix(match).strip().lower()
    before = match.string[max(0, match.start() - 160) : match.start()].lower()
    return prefix.startswith("token:") and "base64 encoded" in before


def _is_token_counter_reference(match: re.Match[str]) -> bool:
    key = _normalized_secret_assignment_key(_matched_secret_key(match))
    if re.fullmatch(r"tokens?_\d+", key) is None:
        return False
    before = _json_escape_compact(match.string[max(0, match.start() - 160) : match.start()]).lower()
    return "writes back" in before or "bucket state" in before


def _is_shell_secret_key_search_reference(match: re.Match[str]) -> bool:
    before = match.string[max(0, match.start() - 120) : match.start()]
    value = _matched_secret_value(match)
    if re.search(r"\b(?:grep|rg)\s+['\"]\^?$", before) is None:
        return False
    return "| cut" in value or "$TMP_WORKSPACE" in value or "$HOME" in value


def _is_escaped_linebreak_whitespace_value(value: str) -> bool:
    if not _starts_with_escaped_or_literal_line_break(value):
        return False
    parts = _ESCAPED_OR_LITERAL_LINE_BREAK_RE.split(value)
    return all(not part.strip("\\").strip() for part in parts)


def _is_public_search_output_secret_heading(match: re.Match[str]) -> bool:
    value = _matched_secret_value(match)
    prefix = _secret_match_prefix(match)
    if not _SEARCH_OUTPUT_SECRET_HEADING_RE.search(prefix):
        return False
    parts = [part.strip().strip("\\") for part in _ESCAPED_OR_LITERAL_LINE_BREAK_RE.split(value)]
    meaningful = [part for part in parts if part and not set(part) <= {"\\", "-", "*", "+"}]
    if not meaningful:
        return False
    for part in meaningful:
        if _segment_has_unsafe_nested_secret(part):
            return False
        if set(part) <= {"\\", "-", "*", "+", "{", "}", "[", "]", "(", ")", ":", ".", ",", "=", "\"", "'", "#"}:
            continue
        if _SHELL_VARIABLE_REFERENCE_RE.fullmatch(part) or _SHELL_VARIABLE_PATH_RE.fullmatch(part):
            continue
        if _SOURCE_LOCATION_SEGMENT_RE.fullmatch(part) or _SHELL_SOURCE_LOCATION_SEGMENT_RE.fullmatch(part):
            continue
        if _PUBLIC_OUTPUT_BANNER_RE.fullmatch(part) or _BENIGN_PUBLIC_FILE_LABEL_RE.fullmatch(part):
            continue
        if _is_natural_section_part(part, allow_lowercase=True):
            continue
        return False
    return True


def _safe_secret_assignment(match: re.Match[str]) -> bool:
    key = _matched_secret_key(match)
    normalized_key = _normalized_secret_assignment_key(key)
    value = _matched_secret_value(match)
    if normalized_key in _NON_SECRET_ASSIGNMENT_KEYS:
        return True
    if _is_code_condition_secret_key_reference(match):
        return True
    if _is_code_fragment_secret_assignment(match):
        return True
    if _is_natural_encoded_token_reference(match):
        return True
    if _is_token_counter_reference(match):
        return True
    if _is_shell_secret_key_search_reference(match):
        return True
    if _is_escaped_linebreak_whitespace_value(value):
        return True
    if SECRET_PLACEHOLDER_RE.fullmatch(value):
        return True
    if _REDACTED_VALUE_RE.fullmatch(value):
        return True
    if _BACKSLASH_ESCAPE_RUN_RE.fullmatch(value):
        return True
    if _is_public_search_output_secret_heading(match):
        return True
    if _is_reference_only_multiline_value(key, value):
        return True
    if _is_mock_fake_api_key_payload(value):
        return True
    if _is_numbered_secret_section(key, value):
        return True
    if _is_natural_language_secret_section(key, value):
        return True
    if not _ENV_VAR_NAME_RE.fullmatch(value):
        return False
    return _is_metadata_reference_key(key)


def _safe_secret_match(kind: str, match: re.Match[str]) -> bool:
    if kind == "api_key" and _MOCK_FAKE_API_KEY_RE.fullmatch(match.group(0)):
        return True
    if kind in _ASSIGNMENT_SECRET_KINDS:
        return _safe_secret_assignment(match)
    return False


def _redact_home_path(match: re.Match[str]) -> str:
    raw = match.group(0)
    if "\\" in raw:
        parts = [part for part in raw.split("\\") if part]
        suffix = parts[3:] if len(parts) > 3 and parts[1] == "Users" else []
        return "%USERPROFILE%" + ("\\" + "\\".join(suffix) if suffix else "")

    parts = [part for part in raw.split("/") if part]
    home_var = "$HOME"
    suffix: list[str] = []
    if len(parts) >= 3 and parts[0] == "data" and parts[1] == "home":
        suffix = parts[3:]
    elif len(parts) >= 2 and parts[0] == "home":
        suffix = parts[2:]
    elif len(parts) >= 2 and parts[0] == "Users":
        suffix = parts[2:]
    elif len(parts) >= 4 and parts[0] == "mnt" and parts[2] == "Users":
        home_var = "$WINDOWS_HOME"
        suffix = parts[4:]
    if suffix and suffix[0] == "ActBench":
        return "$REPO_ROOT" + ("/" + "/".join(suffix[1:]) if len(suffix) > 1 else "")
    return home_var + ("/" + "/".join(suffix) if suffix else "")


def _redact_secret(kind: str, match: re.Match[str]) -> str:
    redaction_kind = "private_provider_url" if kind == "private_provider_url_assignment" else kind
    if kind in _ASSIGNMENT_SECRET_KINDS:
        value = _matched_secret_value(match)
        whole = match.group(0)
        return whole.replace(value, f"<REDACTED_{redaction_kind.upper()}:{_fingerprint(value)}>")
    value = match.group(0)
    return f"<REDACTED_{redaction_kind.upper()}:{_fingerprint(value)}>"


def _redact_private_key_block(match: re.Match[str]) -> str:
    value = match.group(0)
    return f"<REDACTED_PRIVATE_KEY:{_fingerprint(value)}>"


def _redact_ls_owner_group(match: re.Match[str]) -> str:
    return f"{match.group(1)}$USER{match.group(3)}$GROUP{match.group(5)}"


def redact_text(
    text: str,
    *,
    identity_patterns: Sequence[tuple[str, re.Pattern[str]]] | None = None,
) -> str:
    """Return a public-safe copy of a text blob.

    The redactor is intentionally deterministic and conservative: it preserves
    structure while replacing local paths and high-signal credential patterns.
    """

    redacted = _HOME_PATH_RE.sub(_redact_home_path, text)
    redacted = _TMP_PATH_RE.sub("$TMP_WORKSPACE", redacted)
    redacted = _LS_LONG_LINE_RE.sub(_redact_ls_owner_group, redacted)
    redacted = _LOCAL_IDENTITY_ENV_RE.sub(_redact_local_identity_assignment, redacted)
    redacted = _JSON_LOCAL_IDENTITY_FIELD_RE.sub(_redact_local_identity_assignment, redacted)
    redacted = _SSH_IDENTITY_ENV_RE.sub(_redact_ssh_identity_assignment, redacted)
    redacted = _JSON_SSH_IDENTITY_FIELD_RE.sub(_redact_ssh_identity_assignment, redacted)
    patterns = tuple(identity_patterns) if identity_patterns is not None else _local_identity_patterns()
    for kind, pattern in patterns:
        replacement = _LOCAL_HOSTNAME_PLACEHOLDER if kind == "local_hostname" else _LOCAL_USERNAME_PLACEHOLDER
        redacted = pattern.sub(replacement, redacted)
    redacted = _PRIVATE_KEY_BLOCK_RE.sub(_redact_private_key_block, redacted)
    for kind, pattern in _SECRET_PATTERNS:
        if kind == "home_path":
            continue
        redacted = pattern.sub(
            lambda match, item=kind: match.group(0) if _safe_secret_match(item, match) else _redact_secret(item, match),
            redacted,
        )
    return redacted


def _redact_json_value(
    value: Any,
    *,
    identity_patterns: Sequence[tuple[str, re.Pattern[str]]],
) -> Any:
    if isinstance(value, str):
        return redact_text(value, identity_patterns=identity_patterns)
    if isinstance(value, list):
        return [_redact_json_value(item, identity_patterns=identity_patterns) for item in value]
    if isinstance(value, tuple):
        return [_redact_json_value(item, identity_patterns=identity_patterns) for item in value]
    if isinstance(value, dict):
        return {
            redact_text(str(key), identity_patterns=identity_patterns): _redact_json_value(
                item,
                identity_patterns=identity_patterns,
            )
            for key, item in value.items()
        }
    return value


def redact_json(value: Any) -> Any:
    """Recursively redact string leaves in a JSON-like payload."""

    return _redact_json_value(value, identity_patterns=_local_identity_patterns())


_EMBEDDED_CHECKER_PATHS: tuple[tuple[str, ...], ...] = (
    ("task", "automated_checks"),
    ("scoring_inputs", "attack_check_code"),
    ("scoring_inputs", "scene", "attack_check_code"),
    ("task", "frontmatter", "attack_check_code"),
)

# These fields belong to the retired threshold/defense scoring contract.  They
# may still occur in historical trajectories, but they are not part of the
# public AGS/UGS/ASR contract.  Keep this list path-aware: free-form transcript
# and workspace evidence can legitimately quote an old field name.
PUBLIC_LEGACY_SCORING_FIELDS: frozenset[str] = frozenset(
    {
        "attack_success_threshold",
        "defense_pass_condition",
        "defense_score",
        "task_pass",
        "attack_pass",
        "TAcc",
        "tacc",
        "safety_diagnostic",
    }
)
PUBLIC_LEGACY_CLEANUP_VERSION = "actbench.public_legacy_cleanup.v1"


def _strip_legacy_scoring_keys(value: Any, *, path: tuple[str, ...], removed: list[str]) -> None:
    """Remove retired score keys from structured scoring metadata in-place."""

    if isinstance(value, dict):
        for key in list(value):
            key_text = str(key)
            child_path = path + (key_text,)
            if key_text in PUBLIC_LEGACY_SCORING_FIELDS:
                value.pop(key, None)
                removed.append(".".join(child_path))
                continue
            _strip_legacy_scoring_keys(value[key], path=child_path, removed=removed)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _strip_legacy_scoring_keys(item, path=path + (str(index),), removed=removed)


def clean_public_trajectory(
    payload: dict[str, Any],
    *,
    checker_code: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply the current public scoring contract to one trajectory payload.

    The source trajectory remains untouched.  Only structured scoring metadata
    is cleaned; transcript/workspace evidence is preserved byte-for-byte apart
    from the normal privacy redaction pass.  Embedded checker snippets are
    replaced by the authoritative current task grader supplied by the release
    builder, avoiding unsafe regex edits to executable Python.
    """

    cleaned = copy.deepcopy(payload)
    removed: list[str] = []
    scoring_inputs = cleaned.get("scoring_inputs")
    if isinstance(scoring_inputs, dict):
        _strip_legacy_scoring_keys(scoring_inputs, path=("scoring_inputs",), removed=removed)

    replaced: list[str] = []
    for path in _EMBEDDED_CHECKER_PATHS:
        current: Any = cleaned
        for key in path[:-1]:
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(key)
        if not isinstance(current, dict) or path[-1] not in current:
            continue
        if current[path[-1]] in (None, ""):
            continue
        current[path[-1]] = checker_code
        replaced.append(".".join(path))

    return cleaned, {
        "policy_version": PUBLIC_LEGACY_CLEANUP_VERSION,
        "applied": True,
        "removed_fields": sorted(removed),
        "removed_field_count": len(removed),
        "replaced_checker_paths": replaced,
        "replaced_checker_count": len(replaced),
    }


def _payload_path(payload: Any, path: Sequence[str]) -> Any:
    current = payload
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _parse_embedded_checker(code: str, *, label: str) -> ast.AST:
    """Parse an embedded checker after removing JSON string indentation."""

    # Checker snippets are commonly stored as an indented JSON string.  Parsing
    # the raw value would reject valid snippets with an ``IndentationError``.
    return ast.parse(textwrap.dedent(code), filename=label, mode="exec")


def _checker_ast_shape(node: ast.AST) -> Any:
    """Return a syntax shape that ignores expected redactions in string literals."""

    fields: list[tuple[str, Any]] = []
    for name, value in ast.iter_fields(node):
        if isinstance(value, ast.AST):
            value = _checker_ast_shape(value)
        elif isinstance(value, list):
            value = [
                _checker_ast_shape(item) if isinstance(item, ast.AST) else item
                for item in value
            ]
        elif isinstance(node, ast.Constant) and name == "value" and isinstance(value, str):
            # Paths, provider URLs, and secret placeholders inside string
            # literals are allowed to change during redaction.
            value = ("redacted-string",)
        fields.append((name, value))
    return (type(node).__name__, tuple(fields))


def validate_checker_payload(payload: Any, *, label: str = "trajectory") -> list[str]:
    """Validate the syntax of embedded checker fields in one payload."""

    errors: list[str] = []
    for path in _EMBEDDED_CHECKER_PATHS:
        code = _payload_path(payload, path)
        if code in (None, ""):
            continue
        field = ".".join(path)
        if not isinstance(code, str):
            errors.append(f"{label}.{field}: embedded checker must remain a string")
            continue
        try:
            _parse_embedded_checker(code, label=f"{label}:{field}")
        except (SyntaxError, ValueError, TypeError, MemoryError) as exc:
            errors.append(f"{label}.{field}: checker is not valid Python: {exc}")
    return errors


def validate_redacted_checker_payload(
    source_payload: Any,
    redacted_payload: Any,
    *,
    label: str = "trajectory",
) -> list[str]:
    """Validate checker syntax and structure across a redaction operation.

    The historical release failure happened when a regex replacement removed
    the newline/body after an ``if`` statement.  A leak scan cannot see that
    failure, so every embedded checker is parsed before a redacted trajectory
    is accepted.  The AST shape comparison permits string literal contents to
    change while rejecting structural edits and all non-string changes.
    """

    errors: list[str] = []
    for path in _EMBEDDED_CHECKER_PATHS:
        source_code = _payload_path(source_payload, path)
        redacted_code = _payload_path(redacted_payload, path)
        if source_code in (None, "") and redacted_code in (None, ""):
            continue
        field = ".".join(path)
        if not isinstance(source_code, str) or not isinstance(redacted_code, str):
            errors.append(f"{label}.{field}: embedded checker must remain a string")
            continue
        try:
            source_tree = _parse_embedded_checker(source_code, label=f"{label}:{field}:source")
        except (SyntaxError, ValueError, TypeError, MemoryError) as exc:
            errors.append(f"{label}.{field}: source checker is not valid Python: {exc}")
            continue
        try:
            redacted_tree = _parse_embedded_checker(redacted_code, label=f"{label}:{field}:redacted")
        except (SyntaxError, ValueError, TypeError, MemoryError) as exc:
            errors.append(f"{label}.{field}: redacted checker is not valid Python: {exc}")
            continue
        if _checker_ast_shape(source_tree) != _checker_ast_shape(redacted_tree):
            errors.append(f"{label}.{field}: redaction changed checker AST structure")
    return errors


def _is_probably_text(path: Path, max_probe_bytes: int = 8192) -> bool:
    try:
        with path.open("rb") as handle:
            sample = handle.read(max_probe_bytes)
    except OSError:
        return False
    if b"\0" in sample:
        return False
    try:
        text = sample.decode("utf-8")
    except UnicodeDecodeError:
        return False
    if path.suffix.lower() in _TEXT_SUFFIXES:
        return True
    if not text:
        return True
    control_chars = sum(1 for char in text if ord(char) < 32 and char not in "\n\r\t\f\b")
    return control_chars / max(len(text), 1) < 0.05


def write_redacted_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(redact_json(payload), indent=2, ensure_ascii=False), encoding="utf-8")


def _should_omit_internal_artifact(source: Path, *, backend: str = "") -> bool:
    try:
        with source.open("rb") as handle:
            sample = handle.read(4_000_000)
    except OSError:
        return False
    if b"conversation_history" in sample and any(marker in sample for marker in _INTERNAL_HISTORY_SCHEMA_MARKERS[1:]):
        return True
    return source.name.lower() in _OMITTED_INTERNAL_ARTIFACT_NAMES and "qwenpaw" in backend.lower()


def _write_omitted_internal_artifact(destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(_OMITTED_INTERNAL_ARTIFACT_TEXT, encoding="utf-8")


def _write_omitted_symlink(destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(_OMITTED_SYMLINK_TEXT, encoding="utf-8")


def _write_omitted_symlink_directory(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    (destination / _OMITTED_SYMLINK_DIRECTORY_NOTE).write_text(_OMITTED_SYMLINK_TEXT, encoding="utf-8")


def copy_redacted_file(source: Path, destination: Path, *, backend: str = "") -> None:
    """Copy a file to ``destination``, redacting text content when possible."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_symlink():
        _write_omitted_symlink(destination)
        return
    if _should_omit_internal_artifact(source, backend=backend):
        _write_omitted_internal_artifact(destination)
        return
    if _is_probably_text(source):
        try:
            text = source.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            shutil.copy2(source, destination)
            return
        destination.write_text(redact_text(text), encoding="utf-8")
        return
    shutil.copy2(source, destination)


def copy_redacted_tree(source: Path, destination: Path, *, backend: str = "") -> None:
    """Copy a directory tree while redacting text files."""

    if destination.exists():
        if destination.is_dir():
            shutil.rmtree(destination)
        else:
            destination.unlink()
    if source.is_symlink():
        _write_omitted_symlink_directory(destination)
        return
    destination.mkdir(parents=True, exist_ok=True)
    for item in sorted(source.rglob("*"), key=lambda path: path.parts):
        rel = item.relative_to(source)
        target = destination / rel
        if item.is_symlink():
            _write_omitted_symlink(target)
        elif item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif item.is_file():
            copy_redacted_file(item, target, backend=backend)


def _scan_line(
    line: str,
    *,
    path: str,
    line_number: int,
    identity_patterns: Sequence[tuple[str, re.Pattern[str]]] | None = None,
) -> list[RedactionHit]:
    hits = _execution_identity_hits(
        line,
        path=path,
        line_number=line_number,
        identity_patterns=identity_patterns,
    )
    for kind, pattern in _SECRET_PATTERNS:
        for match in pattern.finditer(line):
            raw = match.group(0)
            if _safe_secret_match(kind, match):
                continue
            hits.append(
                RedactionHit(
                    path=path,
                    kind=kind,
                    line=line_number,
                    fingerprint=_fingerprint(f"{kind}:{raw}"),
                )
            )
    return hits


def scan_text(text: str, *, path: str = "") -> list[RedactionHit]:
    """Scan text for high-signal public-release leaks."""

    hits: list[RedactionHit] = []
    identity_patterns = _local_identity_patterns()
    for line_number, line in enumerate(text.splitlines(), start=1):
        hits.extend(
            _scan_line(
                line,
                path=path,
                line_number=line_number,
                identity_patterns=identity_patterns,
            )
        )
    return hits


def _scan_binary_file(
    path: Path,
    *,
    display_path: str,
    chunk_size: int = 1024 * 1024,
    overlap: int = 4096,
    identity_patterns: Sequence[tuple[str, re.Pattern[str]]] | None = None,
) -> list[RedactionHit]:
    hits: list[RedactionHit] = []
    carry = b""
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            payload = carry + chunk
            text = payload.decode("latin-1", errors="ignore")
            hits.extend(
                _execution_identity_hits(
                    text,
                    path=display_path,
                    line_number=None,
                    identity_patterns=identity_patterns,
                )
            )
            for kind, pattern in _SECRET_PATTERNS:
                for match in pattern.finditer(text):
                    raw = match.group(0)
                    if _safe_secret_match(kind, match):
                        continue
                    hits.append(
                        RedactionHit(path=display_path, kind=kind, line=None, fingerprint=_fingerprint(f"{kind}:{raw}"))
                    )
            carry = payload[-overlap:]
    return hits


def _scan_path_label(
    label: str,
    *,
    identity_patterns: Sequence[tuple[str, re.Pattern[str]]] | None = None,
) -> list[RedactionHit]:
    hits = _execution_identity_hits(
        label,
        path=label,
        line_number=None,
        kind_prefix="path_",
        identity_patterns=identity_patterns,
    )
    for kind, pattern in _SECRET_PATTERNS:
        if kind == "home_path":
            continue
        for match in pattern.finditer(label):
            raw = match.group(0)
            if _safe_secret_match(kind, match):
                continue
            hits.append(RedactionHit(path=label, kind=f"path_{kind}", line=None, fingerprint=_fingerprint(f"path:{kind}:{raw}")))
    return hits


def _iter_files(roots: Sequence[Path]) -> Iterable[Path]:
    for root in roots:
        if root.is_symlink() or root.is_file():
            yield root
            continue
        if not root.exists():
            continue
        for path in sorted(root.rglob("*"), key=lambda item: item.parts):
            if path.is_symlink() or path.is_file():
                yield path


def _is_excluded_label(label: str, prefixes: set[str]) -> bool:
    label_parts = Path(label).parts
    for prefix in prefixes:
        prefix_parts = Path(prefix).parts
        if prefix_parts and label_parts[: len(prefix_parts)] == prefix_parts:
            return True
    return False


def scan_release_tree(
    roots: Sequence[Path | str],
    *,
    max_file_bytes: int = 10_000_000,
    exclude_relative_parts: Sequence[str] = (),
) -> RedactionScanResult:
    """Scan public release files for likely leaks.

    Text files, including large JSONL HF shards, are streamed line-by-line so
    the scanner does not miss the actual public payload.  Binary files are
    scanned byte-wise for high-signal token patterns.  ``max_file_bytes`` remains
    as a guard for very large unknown text files.  The result never includes matched
    secret values, only stable fingerprints.
    """

    result = RedactionScanResult()
    excluded = set(exclude_relative_parts)
    identity_patterns = _local_identity_patterns()
    for raw_root in roots:
        root = Path(raw_root).expanduser()
        for path in _iter_files([root]):
            display_path = path.name
            try:
                if root.is_dir():
                    display_path = path.relative_to(root).as_posix()
            except ValueError:
                display_path = path.name
            if _is_excluded_label(display_path, excluded):
                continue
            result.hits.extend(_scan_path_label(display_path, identity_patterns=identity_patterns))
            if path.is_symlink():
                result.hits.append(
                    RedactionHit(
                        path=display_path,
                        kind="symlink",
                        line=None,
                        fingerprint=_fingerprint(f"symlink:{display_path}"),
                    )
                )
                continue
            try:
                size = path.stat().st_size
            except OSError:
                result.skipped_files += 1
                continue
            is_text = _is_probably_text(path)
            if not is_text:
                try:
                    result.scanned_files += 1
                    result.hits.extend(
                        _scan_binary_file(
                            path,
                            display_path=display_path,
                            identity_patterns=identity_patterns,
                        )
                    )
                except OSError:
                    result.skipped_files += 1
                continue
            if size > max_file_bytes and path.suffix.lower() not in _TEXT_SUFFIXES:
                result.skipped_files += 1
                continue
            try:
                with path.open("r", encoding="utf-8", errors="replace") as handle:
                    result.scanned_files += 1
                    for line_number, line in enumerate(handle, start=1):
                        result.hits.extend(
                            _scan_line(
                                line,
                                path=display_path,
                                line_number=line_number,
                                identity_patterns=identity_patterns,
                            )
                        )
            except OSError:
                result.skipped_files += 1
                continue
    return result


def raise_on_redaction_hits(result: RedactionScanResult) -> None:
    if result.ok:
        return
    if not result.hits:
        raise RedactionError(f"Release redaction scan skipped {result.skipped_files} file(s)")
    preview = ", ".join(
        f"{hit.kind}@{hit.path}:{hit.line or '?'}#{hit.fingerprint}" for hit in result.hits[:5]
    )
    suffix = "" if len(result.hits) <= 5 else f", ... ({len(result.hits)} hits total)"
    skipped = f"; skipped_files={result.skipped_files}" if result.skipped_files else ""
    raise RedactionError(f"Release redaction scan found potential leaks: {preview}{suffix}{skipped}")
