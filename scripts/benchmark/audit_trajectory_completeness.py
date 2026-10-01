#!/usr/bin/env python3
"""Audit supplemental trajectory batches against the 900 attack + 300 benign contract.

The supplemental archive keeps only successful executions. This report therefore
labels a slot as ``raw_missing`` when its successful trajectory is absent, and
separately labels score-input mismatches and scorer errors. It never edits source
trajectories or score files.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import tarfile
from collections import Counter
from pathlib import Path
from typing import Any

EXPECTED_ATTACK_RUNS = (1, 2, 3)
MODEL_INFO = {
    "openclaw_gpt-5.4": {
        "label": "GPT-5.4",
        "model": "zju-router/gpt-5.4",
        "attack_score": "gpt54_20260804_offline_score.json",
        "ugs_score": "gpt54_20260804_ugs_score.json",
    },
    "openclaw_gpt-5.6-sol": {
        "label": "GPT-5.6-Sol",
        "model": "zju-router/gpt-5.6-sol",
        "attack_score": "gpt56sol_20260808_offline_score.json",
        "ugs_score": "gpt56sol_20260808_ugs_score.json",
    },
    "openclaw_gpt-5.6-terra": {
        "label": "GPT-5.6-Terra",
        "model": "zju-router/gpt-5.6-terra",
        "attack_score": "gpt56terra_20260807_offline_score.json",
        "ugs_score": "gpt56terra_20260807_ugs_score.json",
    },
    "openclaw_gpt-5.6-luna": {
        "label": "GPT-5.6-Luna",
        "model": "zju-router/gpt-5.6-luna",
        "attack_score": "gpt56luna_20260807_offline_score.json",
        "ugs_score": "gpt56luna_20260807_ugs_score.json",
    },
    "openclaw_grok-4.3": {
        "label": "Grok-4.3",
        "model": "zju-router/grok-4.3",
        "attack_score": "grok43_20260803_retry_offline_score.json",
        "ugs_score": "grok43_20260803_retry_ugs_score.json",
    },
    "openclaw_minimax-m2.5": {
        "label": "MiniMax-M2.5",
        "model": "minimax/MiniMax-M2.5",
        "attack_score": "minimax25_20260803_offline_score.json",
        "ugs_score": "minimax25_20260803_ugs_score.json",
    },
    "openclaw_deepseek-v4-flash-0731": {
        "label": "Deepseek-v4-Flash-0731",
        "model": "deepseek/deepseek-v4-flash-0731",
        "attack_score": "dsv4flash_20260804_offline_score.json",
        "ugs_score": "dsv4flash_20260804_ugs_score.json",
    },
}


def task_sort_key(task_id: str) -> tuple[int, int]:
    match = re.fullmatch(r"task_B(\d+)_T(\d+)", task_id)
    if not match:
        return (10_000, 10_000)
    return (int(match.group(1)), int(match.group(2)))


def slot_sort_key(slot: tuple[str, str, int]) -> tuple[int, int, int]:
    suite, task_id, run_number = slot
    b, t = task_sort_key(task_id)
    return (b, t, run_number)


def load_json_member(tf: tarfile.TarFile, member: tarfile.TarInfo) -> dict[str, Any]:
    value = json.load(tf.extractfile(member))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object in {member.name}")
    return value


def score_status(row: dict[str, Any] | None) -> tuple[str, str]:
    if row is None:
        return "score_row_missing", ""
    if row.get("evaluation_error"):
        return "evaluation_error", str(row.get("error_type") or row.get("execution_status") or "unknown")
    return "valid", ""


def model_sort_key(model: str) -> int:
    return list(MODEL_INFO).index(model)


def build_report(archive: Path, score_dir: Path, output_dir: Path) -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[2]
    task_ids = sorted(
        p.name
        for p in (repo_root / "tasks").iterdir()
        if p.is_dir() and re.fullmatch(r"task_B\d+_T\d+", p.name)
    )
    if len(task_ids) != 300:
        raise RuntimeError(f"expected 300 task directories, found {len(task_ids)}")
    expected_attack = {
        (re.match(r"task_(B\d+)_", task_id).group(1), task_id, run_number)
        for task_id in task_ids
        for run_number in EXPECTED_ATTACK_RUNS
    }
    expected_baseline = set(task_ids)

    raw_attack: dict[str, set[tuple[str, str, int]]] = {model: set() for model in MODEL_INFO}
    raw_baseline: dict[str, set[str]] = {model: set() for model in MODEL_INFO}
    raw_baseline_files: dict[str, dict[str, str]] = {model: {} for model in MODEL_INFO}
    manifest: dict[str, Any]

    with tarfile.open(archive, "r:gz") as tf:
        manifest = load_json_member(tf, tf.getmember("MANIFEST.json"))
        for member in tf:
            name = member.name
            if name.endswith("/trajectory.json") and not name.startswith("benign_baselines/"):
                parts = name.split("/")
                if len(parts) == 6 and parts[0] in MODEL_INFO and parts[4].startswith("run_"):
                    raw_attack[parts[0]].add((parts[1], parts[2], int(parts[4].split("_", 1)[1])))
            elif name.startswith("benign_baselines/") and name.endswith(".json"):
                parts = name.split("/")
                if len(parts) >= 3 and parts[1] in MODEL_INFO:
                    value = load_json_member(tf, member)
                    task_id = str(value.get("source_task_id") or value.get("task_id") or "")
                    if task_id:
                        raw_baseline[parts[1]].add(task_id)
                        raw_baseline_files[parts[1]][task_id] = name

    attack_scores: dict[str, dict[str, dict[str, Any]]] = {}
    ugs_scores: dict[str, dict[str, dict[str, Any]]] = {}
    ugs_excluded: dict[str, list[dict[str, Any]]] = {}
    batches: list[dict[str, Any]] = []
    slot_rows: list[dict[str, Any]] = []

    for archive_model, info in MODEL_INFO.items():
        attack_payload = json.loads((score_dir / info["attack_score"]).read_text(encoding="utf-8"))
        ugs_payload = json.loads((score_dir / info["ugs_score"]).read_text(encoding="utf-8"))
        attack_scores[archive_model] = {
            str(row.get("canonical_slot_id")): row
            for row in attack_payload.get("results", [])
            if row.get("canonical_slot_id")
        }
        ugs_scores[archive_model] = {
            str(row.get("source_task_id") or row.get("task_id")): row
            for row in ugs_payload.get("results", [])
            if row.get("source_task_id") or row.get("task_id")
        }
        ugs_excluded[archive_model] = list(ugs_payload.get("raw_by_task_excluded") or [])

        missing_attack = sorted(expected_attack - raw_attack[archive_model], key=slot_sort_key)
        missing_baseline = sorted(expected_baseline - raw_baseline[archive_model], key=task_sort_key)
        attack_score_errors = []
        attack_score_valid = 0
        score_only_error = []
        for slot_id, row in attack_scores[archive_model].items():
            status, reason = score_status(row)
            if status == "valid":
                attack_score_valid += 1
            else:
                attack_score_errors.append({"slot_id": slot_id, "reason": reason})
                parts = slot_id.split("/")
                raw_slot = (parts[0], parts[1], int(parts[2].split("_", 1)[1])) if len(parts) == 3 else None
                if raw_slot in raw_attack[archive_model]:
                    score_only_error.append({"slot_id": slot_id, "reason": reason})

        raw_not_scored = sorted(set(raw_baseline[archive_model]) - set(ugs_scores[archive_model]), key=task_sort_key)
        score_only_baseline = sorted(set(ugs_scores[archive_model]) - set(raw_baseline[archive_model]), key=task_sort_key)
        excluded_by_task = {
            str(item.get("task_id")): str(item.get("reason") or "excluded")
            for item in ugs_excluded[archive_model]
            if item.get("task_id")
        }
        raw_not_scored_labels = [
            {"task_id": task_id, "reason": excluded_by_task.get(task_id, "score_source_subset_absent")}
            for task_id in raw_not_scored
        ]

        for suite, task_id, run_number in sorted(expected_attack, key=slot_sort_key):
            slot_id = f"{suite}/{task_id}/run_{run_number}"
            raw_present = (suite, task_id, run_number) in raw_attack[archive_model]
            score = attack_scores[archive_model].get(slot_id)
            score_state, score_reason = score_status(score)
            labels: list[str] = []
            if not raw_present:
                labels.append("raw_missing")
            if score_state == "evaluation_error":
                labels.append("attack_score_error")
            if score_state == "score_row_missing":
                labels.append("attack_score_row_missing")
            slot_rows.append(
                {
                    "batch": archive_model,
                    "label": info["label"],
                    "model": info["model"],
                    "role": "attack",
                    "suite": suite,
                    "task_id": task_id,
                    "run_number": run_number,
                    "slot_id": slot_id,
                    "raw_status": "present" if raw_present else "missing_success_trajectory",
                    "score_status": score_state,
                    "score_reason": score_reason,
                    "issue_label": ";".join(labels) or "ok",
                }
            )
        for task_id in sorted(expected_baseline, key=task_sort_key):
            suite = re.match(r"task_(B\d+)_", task_id).group(1)
            raw_present = task_id in raw_baseline[archive_model]
            score_present = task_id in ugs_scores[archive_model]
            labels: list[str] = []
            if not raw_present:
                labels.append("raw_missing")
            if raw_present and not score_present:
                labels.append("ugs_score_not_included")
            if score_present and not raw_present:
                labels.append("ugs_score_outside_archive")
            slot_rows.append(
                {
                    "batch": archive_model,
                    "label": info["label"],
                    "model": info["model"],
                    "role": "benign",
                    "suite": suite,
                    "task_id": task_id,
                    "run_number": 1,
                    "slot_id": f"{suite}/{task_id}/baseline",
                    "raw_status": "present" if raw_present else "missing_success_trajectory",
                    "score_status": "valid" if score_present else "score_row_missing",
                    "score_reason": (
                        excluded_by_task.get(task_id, "score_source_subset_absent")
                        if not score_present
                        else ""
                    ),
                    "issue_label": ";".join(labels) or "ok",
                }
            )

        batches.append(
            {
                "batch": archive_model,
                "label": info["label"],
                "model": info["model"],
                "expected_attack": 900,
                "raw_attack": len(raw_attack[archive_model]),
                "raw_attack_missing": len(missing_attack),
                "expected_benign": 300,
                "raw_benign": len(raw_baseline[archive_model]),
                "raw_benign_missing": len(missing_baseline),
                "raw_total": len(raw_attack[archive_model]) + len(raw_baseline[archive_model]),
                "raw_total_missing": len(missing_attack) + len(missing_baseline),
                "attack_score_rows": len(attack_scores[archive_model]),
                "attack_score_valid": attack_score_valid,
                "attack_score_errors": len(attack_score_errors),
                "attack_score_errors_with_raw": len(score_only_error),
                "ugs_score_rows": len(ugs_scores[archive_model]),
                "raw_benign_not_in_ugs": len(raw_not_scored),
                "ugs_rows_outside_archive": len(score_only_baseline),
                "status": "complete" if not missing_attack and not missing_baseline else "INCOMPLETE",
                "missing_attack_slots": [f"{suite}/{task_id}/run_{run_number}" for suite, task_id, run_number in missing_attack],
                "missing_benign_tasks": missing_baseline,
                "attack_score_errors_detail": attack_score_errors,
                "attack_score_errors_with_raw_detail": score_only_error,
                "raw_benign_not_in_ugs_detail": raw_not_scored_labels,
                "ugs_rows_outside_archive_detail": score_only_baseline,
                "manifest_model_entry": manifest.get("models", {}).get(archive_model, {}),
            }
        )

    raw_attack_total = sum(batch["raw_attack"] for batch in batches)
    raw_benign_total = sum(batch["raw_benign"] for batch in batches)
    report = {
        "schema_version": "actbench.trajectory_completeness.v1",
        "generated_at": "2026-09-29",
        "source_archive": archive.name,
        "contract": {
            "tasks": 300,
            "attack_runs_per_task": 3,
            "expected_attack_per_batch": 900,
            "expected_benign_per_batch": 300,
            "expected_total_per_batch": 1200,
            "expected_attack_all_batches": 6300,
            "expected_benign_all_batches": 2100,
            "expected_total_all_batches": 8400,
        },
        "raw_archive_totals": {
            "attack_present": raw_attack_total,
            "attack_missing": 6300 - raw_attack_total,
            "benign_present": raw_benign_total,
            "benign_missing": 2100 - raw_benign_total,
            "total_present": raw_attack_total + raw_benign_total,
            "total_missing": 8400 - raw_attack_total - raw_benign_total,
        },
        "batches": batches,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "trajectory_completeness.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with (output_dir / "trajectory_slot_labels.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = list(slot_rows[0])
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(slot_rows)
    with (output_dir / "batch_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = [
            "batch", "label", "model", "expected_attack", "raw_attack", "raw_attack_missing",
            "expected_benign", "raw_benign", "raw_benign_missing", "raw_total", "raw_total_missing",
            "attack_score_rows", "attack_score_valid", "attack_score_errors", "attack_score_errors_with_raw",
            "ugs_score_rows", "raw_benign_not_in_ugs", "ugs_rows_outside_archive", "status",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: batch[field] for field in fields} for batch in batches)
    (output_dir / "README.txt").write_text(
        "900 attack + 300 benign completeness labels. See trajectory_completeness.json and CSV files.\n"
        "raw_missing means the supplemental archive kept no successful trajectory for that expected slot.\n"
        "ugs_score_not_included means a benign file exists in the supplemental archive but was not in the imported UGS score input.\n",
        encoding="utf-8",
    )
    return report


def compact_list(values: list[str], width: int = 110) -> list[str]:
    lines: list[str] = []
    current = ""
    for value in values:
        if not current:
            current = value
        elif len(current) + 1 + len(value) <= width:
            current += " " + value
        else:
            lines.append(current)
            current = value
    if current:
        lines.append(current)
    return lines


def render_markdown(report: dict[str, Any]) -> str:
    totals = report["raw_archive_totals"]
    lines = [
        "# 补充批次轨迹完整性核对",
        "",
        "本报告按每个新增模型批次应有 **900 条攻击轨迹 + 300 条 benign baseline = 1,200 条** 的规则核对。",
        "归档只保留执行成功的轨迹，因此 `raw_missing` 表示预期 slot 没有成功轨迹文件；它不是补成失败分数。",
        "",
        f"来源归档：`{report['source_archive']}`。7 个批次应有 8,400 条，实际归档 8,306 条，缺 **{totals['total_missing']} 条**：攻击缺 {totals['attack_missing']} 条，benign 缺 {totals['benign_missing']} 条。",
        "",
        "## 批次总览",
        "",
        "| 批次 | 模型 | 攻击 raw | benign raw | 实际总数 | 缺失总数 | 攻击评分 valid/error | UGS 行数 | 标记 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for batch in report["batches"]:
        lines.append(
            f"| `{batch['batch']}` | {batch['label']} | {batch['raw_attack']}/900 (-{batch['raw_attack_missing']}) | "
            f"{batch['raw_benign']}/300 (-{batch['raw_benign_missing']}) | {batch['raw_total']}/1200 | "
            f"-{batch['raw_total_missing']} | {batch['attack_score_valid']}/{batch['attack_score_errors']} | "
            f"{batch['ugs_score_rows']}/300 | **{batch['status']}** |"
        )
    lines += [
        "",
        "`UGS 行数`是已导入 UGS 评分文件中的 benign 行数，不等同于归档中的 benign 文件数。归档文件存在但没有 UGS 行的 task 在下方标为 `ugs_score_not_included`。",
        "",
        "## 逐批次标记",
        "",
    ]
    for batch in report["batches"]:
        lines += [f"### {batch['label']} (`{batch['batch']}`)", ""]
        lines.append(
            f"归档：攻击 {batch['raw_attack']}/900，benign {batch['raw_benign']}/300，共 {batch['raw_total']}/1200；"
            f"缺失 {batch['raw_total_missing']}。攻击评分 valid/error = {batch['attack_score_valid']}/{batch['attack_score_errors']}；"
            f"其中已有 raw 但评分失败 {batch['attack_score_errors_with_raw']} 条。UGS 评分行 {batch['ugs_score_rows']}/300。"
        )
        missing_attack = batch["missing_attack_slots"]
        if missing_attack:
            lines += ["", "**raw 缺失的攻击 slot：**", ""]
            lines.extend(f"`{line}`" for line in compact_list(missing_attack))
        else:
            lines += ["", "攻击 slot：没有缺失。"]
        missing_benign = batch["missing_benign_tasks"]
        if missing_benign:
            lines += ["", "**raw 缺失的 benign task：**", "", " ".join(f"`{x}`" for x in missing_benign)]
        else:
            lines += ["", "benign task：没有 raw 缺失。"]
        errors = batch["attack_score_errors_with_raw_detail"]
        if errors:
            lines += ["", "**有 raw 但攻击评分失败：**", ""]
            lines.extend(f"`{x['slot_id']}` ({x['reason']})" for x in errors)
        not_scored = batch["raw_benign_not_in_ugs_detail"]
        if not_scored:
            lines += ["", f"**归档中存在、但 UGS 未纳入的 benign task（{len(not_scored)} 条）：**", ""]
            lines.append(" ".join(f"`{x['task_id']}`[{x['reason']}]" for x in not_scored))
        outside = batch["ugs_rows_outside_archive_detail"]
        if outside:
            lines += ["", f"**UGS 中有、归档中没有的 benign task（{len(outside)} 条）：**", ""]
            lines.append(" ".join(f"`{x}`" for x in outside))
        lines.append("")
    lines += [
        "## 如何使用机器可读标记",
        "",
        "完整的 8,400 个预期 slot 标签在 `results/imported_server_scores/20260924/completeness_audit_20260929/trajectory_slot_labels.csv`。每行包含 `raw_status`、`score_status` 和 `issue_label`。批次汇总在同目录的 `batch_summary.csv`，原始 JSON 在 `trajectory_completeness.json`。",
        "",
        "这份核对只标记现状，没有把缺失 slot 补成失败轨迹，也没有修改评分文件。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=Path("agent_trajectories_mine_20260925.tar.gz"))
    parser.add_argument("--score-dir", type=Path, default=Path("results/imported_server_scores/20260924"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/imported_server_scores/20260924/completeness_audit_20260929"))
    parser.add_argument("--markdown", type=Path, default=Path("docs/TRAJECTORY_COMPLETENESS_20260925.md"))
    args = parser.parse_args()
    report = build_report(args.archive, args.score_dir, args.output_dir)
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps(report["raw_archive_totals"], ensure_ascii=False, indent=2))
    for batch in report["batches"]:
        print(
            f"{batch['label']}: attack {batch['raw_attack']}/900, benign {batch['raw_benign']}/300, "
            f"total {batch['raw_total']}/1200, UGS {batch['ugs_score_rows']}/300"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
