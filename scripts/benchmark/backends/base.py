"""Common backend protocol types for ActBench target-agent adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Protocol

from lib_tasks import Task


class BackendInitializationError(RuntimeError):
    """Raised when a selected backend cannot be initialized."""


@dataclass(frozen=True)
class BackendRunContext:
    """Per-run data shared with backend adapters."""

    backend: str
    model: str
    run_id: str
    run_root: Path
    skill_dir: Path
    agent_id: str
    agent_workspace: Path
    timeout_multiplier: float
    verbose: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


class AgentBackend(Protocol):
    """Minimal target-agent backend interface consumed by the benchmark runner."""

    name: str
    uses_gateway_lock: bool
    supports_parallel_runs: bool

    def slugify_model(self, model_id: str) -> str:
        """Return the model slug used in result/artifact paths."""

    def make_agent_id(self, model_id: str) -> str:
        """Return the run-scoped agent id used for locking and artifacts."""

    def initialize_run(self, context: BackendRunContext) -> None:
        """Prepare backend-level state before tasks execute."""

    def finalize_run(self, context: BackendRunContext) -> None:
        """Clean up backend-level state after the run completes."""

    def execute_task(
        self,
        *,
        task: Task,
        context: BackendRunContext,
        attempt_run_id: str,
    ) -> Dict[str, Any]:
        """Execute one task attempt and return an ActBench execution result dict."""


def default_slugify_model(model_id: str) -> str:
    """Backend-neutral model slug compatible with the historical OpenClaw slug."""

    return model_id.replace("/", "-").replace(".", "-").lower()


def default_agent_id(model_id: str) -> str:
    """Return the historical benchmark agent id for a model."""

    return f"bench-{default_slugify_model(model_id)}"


def backend_metadata(context: BackendRunContext, **extra: Any) -> Dict[str, Any]:
    """Build standard backend metadata for result payloads."""

    metadata: Dict[str, Any] = {
        "name": context.backend,
        "model": context.model,
        "agent_id": context.agent_id,
    }
    metadata.update(context.metadata)
    metadata.update({key: value for key, value in extra.items() if value is not None})
    return metadata


def augment_execution_result(
    result: Dict[str, Any],
    *,
    context: BackendRunContext,
    **metadata: Any,
) -> Dict[str, Any]:
    """Add backend metadata to an execution result without changing core fields."""

    result.setdefault("backend", context.backend)
    existing = result.get("backend_metadata")
    merged = backend_metadata(context, **metadata)
    if isinstance(existing, dict):
        merged.update(existing)
    result["backend_metadata"] = merged
    return result
