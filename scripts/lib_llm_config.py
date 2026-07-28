"""
Local support-model provider configuration for ActBench.

Committed code only knows generic provider profiles. Private gateway names,
endpoints, and API-key environment variables should live in an ignored local
YAML file, not in the repository.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT / "config" / "llm_backends.local.yaml"
CONFIG_PATH_ENV = "ACTBENCH_LLM_BACKENDS_CONFIG"


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    prefix: str
    api_key_env: str
    base_url_env: str | None = None
    base_url: str | None = None
    strip_prefix: bool = True
    label: str | None = None
    retry_without_temperature: bool = True
    thinking_model_keys: tuple[str, ...] = field(default_factory=tuple)
    min_thinking_max_tokens: int = 16384
    min_thinking_timeout_seconds: float = 300.0

    @property
    def display_name(self) -> str:
        return self.label or self.name

    def api_base(self) -> str:
        if self.base_url_env:
            value = os.environ.get(self.base_url_env, "").strip()
            if value:
                return value.rstrip("/")
        if self.base_url:
            return self.base_url.rstrip("/")
        env_hint = self.base_url_env or "<base_url_env>"
        raise RuntimeError(
            f"Base URL is not configured for LLM provider '{self.name}'. "
            f"Set {env_hint} or provide base_url in the local provider config."
        )

    def api_key(self) -> str:
        key = os.environ.get(self.api_key_env, "")
        if not key:
            raise RuntimeError(
                f"{self.api_key_env} environment variable is not set. "
                f"Set it to use LLM provider '{self.name}'."
            )
        return key


def config_path() -> Path:
    configured = os.environ.get(CONFIG_PATH_ENV, "").strip()
    if configured:
        return Path(configured).expanduser()
    return DEFAULT_CONFIG_PATH


def load_provider_configs(path: Path | None = None) -> list[ProviderConfig]:
    path = path or config_path()
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"LLM provider config {path} must contain a mapping")

    providers = payload.get("providers", {})
    if not isinstance(providers, dict):
        raise ValueError(f"LLM provider config {path} field 'providers' must be a mapping")

    configs: list[ProviderConfig] = []
    for name, raw in providers.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"LLM provider config {path} contains an invalid provider name")
        if not isinstance(raw, dict):
            raise ValueError(f"LLM provider '{name}' in {path} must be a mapping")

        prefix = _required_str(raw, "prefix", name, path)
        api_key_env = _required_str(raw, "api_key_env", name, path)
        thinking_keys = raw.get("thinking_model_keys", ()) or ()
        if isinstance(thinking_keys, str):
            thinking_keys = [thinking_keys]
        if not isinstance(thinking_keys, (list, tuple)) or not all(
            isinstance(item, str) for item in thinking_keys
        ):
            raise ValueError(
                f"LLM provider '{name}' in {path} field 'thinking_model_keys' must be a list of strings"
            )

        configs.append(
            ProviderConfig(
                name=name,
                prefix=prefix,
                api_key_env=api_key_env,
                base_url_env=_optional_str(raw, "base_url_env"),
                base_url=_optional_str(raw, "base_url"),
                strip_prefix=bool(raw.get("strip_prefix", True)),
                label=_optional_str(raw, "label"),
                retry_without_temperature=bool(raw.get("retry_without_temperature", True)),
                thinking_model_keys=tuple(thinking_keys),
                min_thinking_max_tokens=int(raw.get("min_thinking_max_tokens", 16384)),
                min_thinking_timeout_seconds=float(raw.get("min_thinking_timeout_seconds", 300.0)),
            )
        )
    return configs


def match_provider(model: str, path: Path | None = None) -> ProviderConfig | None:
    model_lower = (model or "").lower()
    for provider in load_provider_configs(path):
        if model_lower.startswith(provider.prefix.lower()):
            return provider
    return None


def _required_str(raw: dict[str, Any], key: str, name: str, path: Path) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"LLM provider '{name}' in {path} must set non-empty '{key}'")
    return value.strip()


def _optional_str(raw: dict[str, Any], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Optional field '{key}' must be a string when set")
    value = value.strip()
    return value or None
