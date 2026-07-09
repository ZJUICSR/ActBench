"""Backend registry for ActBench target-agent adapters."""

from __future__ import annotations

from benchmark.backends.base import AgentBackend

_BACKEND_NAMES = ("openclaw", "qwenpaw", "fake")


def available_backend_names() -> tuple[str, ...]:
    """Return backend names accepted by the CLI."""

    return _BACKEND_NAMES


def get_backend(name: str | None) -> AgentBackend:
    """Instantiate a backend by name using lazy imports."""

    normalized = (name or "openclaw").strip().lower()
    if normalized == "openclaw":
        from benchmark.backends.openclaw import OpenClawBackend

        return OpenClawBackend()
    if normalized == "qwenpaw":
        from benchmark.backends.qwenpaw import QwenPawBackend

        return QwenPawBackend()
    if normalized == "fake":
        from benchmark.backends.fake import FakeBackend

        return FakeBackend()
    known = ", ".join(_BACKEND_NAMES)
    raise ValueError(f"unknown backend {name!r}; expected one of: {known}")
