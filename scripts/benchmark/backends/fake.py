"""Deterministic fake backend used by tests and local plumbing checks."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List

from lib_tasks import Task

from benchmark.backends.base import (
    BackendRunContext,
    augment_execution_result,
    default_agent_id,
    default_slugify_model,
)
from benchmark.backends.common import (
    backend_task_workspace,
    begin_task_artifacts,
    elapsed_since,
    execution_error_result,
    finish_task_artifacts,
    materialize_task_workspace,
    session_prompts,
    start_declared_api_services,
    zero_usage,
)

logger = logging.getLogger(__name__)


class FakeBackend:
    """Backend that simulates an agent without external dependencies."""

    name = "fake"
    uses_gateway_lock = False

    def slugify_model(self, model_id: str) -> str:
        return default_slugify_model(model_id)

    def make_agent_id(self, model_id: str) -> str:
        return default_agent_id(model_id)

    def initialize_run(self, context: BackendRunContext) -> None:
        context.agent_workspace.mkdir(parents=True, exist_ok=True)

    def finalize_run(self, context: BackendRunContext) -> None:
        return None

    def execute_task(
        self,
        *,
        task: Task,
        context: BackendRunContext,
        attempt_run_id: str,
    ) -> Dict[str, Any]:
        logger.info("🤖 Fake backend [%s] starting task: %s", context.agent_id, task.task_id)
        start_time = time.time()
        session_id = f"{task.task_id}_{int(start_time * 1000)}"
        workspace = backend_task_workspace(context=context, attempt_run_id=attempt_run_id, task=task)
        api_group = None
        api_endpoints: Dict[str, Any] = {}
        api_audit: Dict[str, Any] = {}

        try:
            materialize_task_workspace(workspace=workspace, skill_dir=context.skill_dir, task=task)
        except Exception as exc:  # noqa: BLE001 - convert setup issues to execution result
            return execution_error_result(
                context=context,
                task=task,
                workspace=workspace,
                stderr=f"fake backend workspace setup failed: {exc}",
                execution_time=elapsed_since(start_time),
            )

        artifact_key, recorder = begin_task_artifacts(
            context=context,
            task=task,
            attempt_run_id=attempt_run_id,
            session_id=session_id,
            workspace=workspace,
        )

        try:
            try:
                api_group, api_endpoints = start_declared_api_services(
                    task=task,
                    attempt_run_id=attempt_run_id,
                    workspace=workspace,
                )
            except Exception as exc:  # noqa: BLE001
                stderr = f"mock API service startup failed: {exc}"
                return execution_error_result(
                    context=context,
                    task=task,
                    workspace=workspace,
                    stderr=stderr,
                    execution_time=elapsed_since(start_time),
                    api_endpoints=api_endpoints,
                    training_artifact_key=artifact_key,
                )

            prompts = session_prompts(task)
            transcript: List[Dict[str, Any]] = []
            for index, prompt in enumerate(prompts, 1):
                transcript.append(
                    {
                        "type": "message",
                        "message": {"role": "user", "content": [prompt]},
                    }
                )
                transcript.append(
                    {
                        "type": "message",
                        "message": {
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "text",
                                    "text": (
                                        f"Fake backend completed {task.task_id} "
                                        f"turn {index}/{len(prompts)}."
                                    ),
                                }
                            ],
                        },
                    }
                )

            if api_group:
                api_audit = api_group.collect_audit()

            execution_time = elapsed_since(start_time)
            result = {
                "agent_id": context.agent_id,
                "task_id": task.task_id,
                "status": "success",
                "transcript": transcript,
                "usage": zero_usage(request_count=len(prompts)),
                "workspace": str(workspace),
                "exit_code": 0,
                "timed_out": False,
                "execution_time": execution_time,
                "stdout": "",
                "stderr": "",
                "api_audit": api_audit,
                "api_endpoints": api_endpoints,
                "training_artifact_key": artifact_key,
            }
            return augment_execution_result(result, context=context, transcript_source="fake")
        finally:
            if api_group:
                api_group.stop()
            finish_task_artifacts(
                recorder=recorder,
                artifact_key=artifact_key,
                task=task,
                workspace=workspace,
                api_endpoints=api_endpoints,
                api_audit=api_audit,
            )
