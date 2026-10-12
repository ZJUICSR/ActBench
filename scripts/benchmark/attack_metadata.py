"""Canonical attack-scoring metadata helpers."""

from __future__ import annotations

from typing import Any, Dict, Optional


def canonical_attack_goal_from_metadata(
    *,
    frontmatter: Optional[Dict[str, Any]] = None,
    task_attack_goal: Any = None,
    expected_behavior: Any = None,
    task_prompt: Any = None,
    fallback_goal: Any = None,
    fallback_scene_goal: Any = None,
) -> str:
    """Return the attack objective, separating it from a benign boundary note.

    A few legacy B8 tasks used ``attack_goal`` for a defensive instruction
    ("must not execute ...") while the actual attack objective was declared by
    the risk target and checker canary. When that shape is detected, the
    forbidden outcome becomes the objective supplied to AGS/LLM scoring.
    """

    fm = frontmatter if isinstance(frontmatter, dict) else {}
    goal = (
        fm.get("attack_goal")
        or task_attack_goal
        or fm.get("risk_goal")
        or fallback_goal
        or fallback_scene_goal
        or expected_behavior
        or task_prompt
        or ""
    )
    if not isinstance(goal, str):
        goal = str(goal)
    target = fm.get("risk_target") if isinstance(fm.get("risk_target"), dict) else {}
    forbidden = target.get("forbidden_outcomes") if isinstance(target, dict) else None
    lowered = goal.casefold()
    defensive_boundary = (
        isinstance(forbidden, list)
        and bool(forbidden)
        and (
            "must only" in lowered
            or lowered.startswith("the agent must not")
            or "must not execute" in lowered[:220]
        )
        and "attacker" not in lowered
        and "attack" not in lowered
    )
    if defensive_boundary:
        outcomes = "; ".join(str(item) for item in forbidden if item)
        if outcomes:
            return f"Attack success is observed when: {outcomes}"
    return goal
