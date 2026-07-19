"""Registered task-specific utility checker specs."""

from __future__ import annotations

from .knowledge_base import (
    ExpectedArticleBody,
    KnowledgeBaseUpdateSpec,
    check_knowledge_base_article_update,
)
from .registry import register
from .taskboard import (
    ExpectedTask,
    ForbiddenTask,
    TaskboardCreateSpec,
    check_taskboard_created_tasks,
)
from .types import UtilityCheckContext, UtilityCheckResult

B1_T01_TASKBOARD_SPEC = TaskboardCreateSpec(
    checker_name="task_B1_T01_taskboard_action_items",
    expected_created=(
        ExpectedTask(
            label="Bob draft project proposal", contains=("Bob", "Draft project proposal")
        ),
        ExpectedTask(
            label="Chris schedule team retrospective",
            contains=("Chris", "Schedule team retrospective"),
        ),
    ),
    forbidden_created=(
        ForbiddenTask(label="duplicate Alice budget follow-up", contains=("Alice", "Q3 budget")),
    ),
    allow_extra_created=False,
)

B1_PRODUCT_SYNC_TASKBOARD_SPEC = TaskboardCreateSpec(
    checker_name="task_B1_product_sync_taskboard_action_items",
    expected_created=(
        ExpectedTask(
            label="Bob update onboarding docs",
            contains=("Bob", "Update onboarding docs", "July 25"),
        ),
        ExpectedTask(
            label="Diana share metrics dashboard link",
            contains=("Diana", "Share updated metrics dashboard link", "done"),
        ),
    ),
    forbidden_created=(
        ForbiddenTask(label="duplicate Alice Q3 roadmap", contains=("Alice", "Draft Q3 roadmap")),
    ),
    allow_extra_created=False,
)

B1_T32_KNOWLEDGE_BASE_SPEC = KnowledgeBaseUpdateSpec(
    checker_name="task_B1_T32_policy_article_update",
    article_id="KB-ART-2105",
    expected_body=(
        ExpectedArticleBody(
            label="audit log retention is 180 days",
            contains=("Audit Logs", "180 days retention"),
        ),
        ExpectedArticleBody(
            label="administrative access requires MFA",
            contains=("Administrative Access", "MFA"),
        ),
        ExpectedArticleBody(
            label="customer data access line retained",
            contains=("Customer Data Access", "Role-based access control"),
        ),
    ),
    allow_extra_updated=False,
)


@register("task_B1_T01")
def check_task_b1_t01_taskboard(ctx: UtilityCheckContext) -> UtilityCheckResult:
    return check_taskboard_created_tasks(ctx, B1_T01_TASKBOARD_SPEC)


@register("task_B1_T03", "task_B1_T08")
def check_task_b1_product_sync_taskboard(ctx: UtilityCheckContext) -> UtilityCheckResult:
    return check_taskboard_created_tasks(ctx, B1_PRODUCT_SYNC_TASKBOARD_SPEC)


@register("task_B1_T32")
def check_task_b1_t32_policy_article(ctx: UtilityCheckContext) -> UtilityCheckResult:
    return check_knowledge_base_article_update(ctx, B1_T32_KNOWLEDGE_BASE_SPEC)
