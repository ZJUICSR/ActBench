"""OpenClaw backend adapter preserving the historical ActBench execution path."""

from __future__ import annotations

from typing import Any, Dict

from lib_agent import cleanup_agent_sessions, ensure_agent_exists, execute_openclaw_task, slugify_model
from lib_tasks import Task

from benchmark.backends.base import BackendRunContext, augment_execution_result


class OpenClawBackend:
    """Backend wrapper around the existing OpenClaw implementation."""

    name = "openclaw"
    uses_gateway_lock = True

    def slugify_model(self, model_id: str) -> str:
        return slugify_model(model_id)

    def make_agent_id(self, model_id: str) -> str:
        return f"bench-{self.slugify_model(model_id)}"

    def initialize_run(self, context: BackendRunContext) -> None:
        ensure_agent_exists(context.agent_id, context.model, context.agent_workspace)
        cleanup_agent_sessions(context.agent_id)

    def finalize_run(self, context: BackendRunContext) -> None:
        return None

    def execute_task(
        self,
        *,
        task: Task,
        context: BackendRunContext,
        attempt_run_id: str,
    ) -> Dict[str, Any]:
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
