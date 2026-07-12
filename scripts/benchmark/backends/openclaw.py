"""OpenClaw backend adapter preserving the historical ActBench execution path."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Dict

from lib_agent import (
    cleanup_agent_sessions,
    ensure_agent_exists,
    execute_openclaw_task,
    slugify_model,
)
from lib_gateway_lock import GatewayLockConflict
from lib_gateway_lock import acquire as acquire_gateway_lock
from lib_gateway_lock import release as release_gateway_lock
from lib_tasks import Task

from benchmark.backends.base import (
    BackendInitializationError,
    BackendRunContext,
    augment_execution_result,
)

logger = logging.getLogger(__name__)


@dataclass
class _OpenClawLane:
    worker_id: int
    agent_id: str
    workspace: Path
    lock: threading.Lock


class OpenClawBackend:
    """Backend wrapper around the existing OpenClaw implementation."""

    name = "openclaw"
    uses_gateway_lock = True
    supports_parallel_runs = True

    def __init__(self) -> None:
        self._lanes: Dict[int, _OpenClawLane] = {}
        self._lane_gateway_locks: list[str] = []

    def slugify_model(self, model_id: str) -> str:
        return slugify_model(model_id)

    def make_agent_id(self, model_id: str) -> str:
        return f"bench-{self.slugify_model(model_id)}"

    def _run_workers(self, context: BackendRunContext) -> int:
        return int(context.metadata.get("run_workers", 1) or 1)

    def _uses_parallel_lanes(self, context: BackendRunContext) -> bool:
        return self._run_workers(context) > 1

    def _lane_agent_id(self, model_id: str, worker_id: int) -> str:
        return f"{self.make_agent_id(model_id)}-rep{worker_id}"

    def _lane_workspace(self, context: BackendRunContext, worker_id: int) -> Path:
        return context.run_root / context.run_id / "agent_workspaces" / f"rep{worker_id}"

    def _reset_lane_state(self) -> None:
        self._lanes.clear()
        self._lane_gateway_locks.clear()

    def _release_lane_gateway_locks(self) -> None:
        for agent_id in list(self._lane_gateway_locks):
            try:
                release_gateway_lock(agent_id)
            except Exception as exc:  # pragma: no cover - defensive cleanup logging
                logger.warning("Failed to release OpenClaw lane gateway lock %s: %s", agent_id, exc)

    def initialize_run(self, context: BackendRunContext) -> None:
        self._release_lane_gateway_locks()
        self._reset_lane_state()

        if not self._uses_parallel_lanes(context):
            ensure_agent_exists(context.agent_id, context.model, context.agent_workspace)
            cleanup_agent_sessions(context.agent_id)
            return

        command = str(context.metadata.get("command", "") or "")
        try:
            for worker_id in range(1, self._run_workers(context) + 1):
                agent_id = self._lane_agent_id(context.model, worker_id)
                workspace = self._lane_workspace(context, worker_id)
                acquire_gateway_lock(
                    agent_id,
                    role="actbench",
                    model=context.model,
                    worker_id=worker_id,
                    command=command,
                )
                self._lane_gateway_locks.append(agent_id)
                ensure_agent_exists(agent_id, context.model, workspace)
                cleanup_agent_sessions(agent_id)
                self._lanes[worker_id] = _OpenClawLane(
                    worker_id=worker_id,
                    agent_id=agent_id,
                    workspace=workspace,
                    lock=threading.Lock(),
                )
        except GatewayLockConflict as exc:
            self.finalize_run(context)
            raise BackendInitializationError(str(exc)) from exc
        except Exception:
            self.finalize_run(context)
            raise

    def finalize_run(self, context: BackendRunContext) -> None:
        try:
            self._release_lane_gateway_locks()
        finally:
            self._reset_lane_state()

    def execute_task(
        self,
        *,
        task: Task,
        context: BackendRunContext,
        attempt_run_id: str,
    ) -> Dict[str, Any]:
        if not self._uses_parallel_lanes(context):
            result = execute_openclaw_task(
                task=task,
                agent_id=context.agent_id,
                model_id=context.model,
                run_id=attempt_run_id,
                timeout_multiplier=context.timeout_multiplier,
                skill_dir=context.skill_dir,
                verbose=context.verbose,
            )
            return augment_execution_result(result, context=context)

        worker_id = int(context.metadata.get("run_worker_id", 1) or 1)
        lane = self._lanes.get(worker_id)
        if lane is None:
            raise RuntimeError(f"OpenClaw repeat lane {worker_id} has not been initialized")

        with lane.lock:
            result = execute_openclaw_task(
                task=task,
                agent_id=lane.agent_id,
                model_id=context.model,
                run_id=attempt_run_id,
                timeout_multiplier=context.timeout_multiplier,
                skill_dir=context.skill_dir,
                verbose=context.verbose,
            )
        lane_context = replace(context, agent_id=lane.agent_id, agent_workspace=lane.workspace)
        return augment_execution_result(
            result,
            context=lane_context,
            openclaw_base_agent_id=context.agent_id,
            openclaw_lane_id=f"rep{worker_id}",
            openclaw_lane_agent_id=lane.agent_id,
            openclaw_lane_workspace=str(lane.workspace),
        )
