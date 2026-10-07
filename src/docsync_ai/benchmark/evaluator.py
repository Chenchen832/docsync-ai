"""Metrics, location evaluation, and exports for the controlled benchmark."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from docsync_ai.benchmark.dataset import (
    BENCHMARK_VERSION,
    deterministic_cases,
    semantic_cases,
)
from docsync_ai.services import analyze_project


def classification_metrics(*, tp: int, fp: int, fn: int, tn: int) -> dict[str, Any]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    accuracy = (tp + tn) / (tp + fp + fn + tn) if tp + fp + fn + tn else 0.0
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
        "accuracy": round(accuracy, 6),
    }


def generate_benchmark(benchmark_root: str | Path) -> dict[str, Any]:
    root = Path(benchmark_root)
    cases_root = root / "cases" / "deterministic"
    semantic_root = root / "cases" / "semantic"
    ground_truth_root = root / "ground_truth"
    for directory in (
        cases_root,
        semantic_root,
        ground_truth_root,
        root / "results",
        root / "scripts",
    ):
        directory.mkdir(parents=True, exist_ok=True)

    deterministic = deterministic_cases()
    semantic = semantic_cases()
    for case in deterministic:
        case_dir = cases_root / case.case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        for relative_path, content in case.files.items():
            target = case_dir / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        (case_dir / "case.json").write_text(
            json.dumps(case.ground_truth(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    for case in semantic:
        (semantic_root / f"{case['case_id']}.json").write_text(
            json.dumps(case, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    deterministic_payload = {
        "benchmark_version": BENCHMARK_VERSION,
        "benchmark_type": "deterministic",
        "cases": [case.ground_truth() for case in deterministic],
    }
    semantic_payload = {
        "benchmark_version": BENCHMARK_VERSION,
        "benchmark_type": "semantic",
        "cases": semantic,
    }
    combined = {
        "benchmark_version": BENCHMARK_VERSION,
        "deterministic_cases": deterministic_payload["cases"],
        "semantic_cases": semantic,
    }
    _write_frozen_json(ground_truth_root / "deterministic_ground_truth.json", deterministic_payload)
    _write_frozen_json(ground_truth_root / "semantic_ground_truth.json", semantic_payload)
    combined_path = ground_truth_root / "benchmark_ground_truth.json"
    _write_frozen_json(combined_path, combined)
    digest = hashlib.sha256(combined_path.read_bytes()).hexdigest()
    return {
        "benchmark_version": BENCHMARK_VERSION,
        "deterministic_cases": len(deterministic),
        "semantic_cases": len(semantic),
        "ground_truth_sha256": digest,
    }


def _write_frozen_json(path: Path, payload: dict[str, Any]) -> None:
    content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != content:
        raise ValueError(f"Frozen Ground Truth differs from generated {BENCHMARK_VERSION}: {path}")
    path.write_text(content, encoding="utf-8")


def evaluate_benchmark(benchmark_root: str | Path) -> dict[str, Any]:
    root = Path(benchmark_root)
    ground_truth_path = root / "ground_truth" / "deterministic_ground_truth.json"
    payload = json.loads(ground_truth_path.read_text(encoding="utf-8"))
    if payload.get("benchmark_version") != BENCHMARK_VERSION:
        raise ValueError("Unsupported benchmark version")
    rows = []
    for truth in payload.get("cases", []):
        case_dir = root / "cases" / "deterministic" / truth["case_id"]
        started = time.perf_counter()
        report = analyze_project(case_dir, ai_mode="off")
        elapsed_ms = (time.perf_counter() - started) * 1000
        matching = [
            item
            for item in report["findings"]
            if item["rule_id"] == truth["category"]
            and item["issue_type"] == truth["expected_issue_type"]
        ]
        predicted = bool(matching)
        expected = bool(truth["expected_finding"])
        outcome = _outcome(expected=expected, predicted=predicted)
        finding = matching[0] if matching else None
        location = _location_result(truth, finding) if outcome == "TP" else None
        rows.append(
            {
                "case_id": truth["case_id"],
                "category": truth["category"],
                "expected_finding": expected,
                "predicted_finding": predicted,
                "outcome": outcome,
                "finding_count": len(matching),
                "doc_file_correct": location["doc_file_correct"] if location else None,
                "doc_line_within_2": location["doc_line_within_2"] if location else None,
                "code_entity_correct": location["code_entity_correct"] if location else None,
                "analysis_time_ms": round(elapsed_ms, 6),
                "scanned_files": report["summary"]["scanned_files"],
                "notes": truth["notes"],
            }
        )
    return _aggregate(rows, ground_truth_path)


def _outcome(*, expected: bool, predicted: bool) -> str:
    if expected and predicted:
        return "TP"
    if not expected and predicted:
        return "FP"
    if expected and not predicted:
        return "FN"
    return "TN"


def _location_result(truth: dict[str, Any], finding: dict[str, Any]) -> dict[str, bool]:
    expected_line = truth.get("expected_doc_line")
    actual_line = finding.get("doc_location", {}).get("line_start")
    code_fact_text = json.dumps(finding.get("code_fact"), ensure_ascii=False)
    return {
        "doc_file_correct": (
            Path(finding.get("doc_location", {}).get("file_path", "")).name
            == truth.get("expected_doc_file")
        ),
        "doc_line_within_2": (
            isinstance(expected_line, int)
            and isinstance(actual_line, int)
            and abs(expected_line - actual_line) <= 2
        ),
        "code_entity_correct": str(truth.get("expected_code_entity", "")) in code_fact_text,
    }


def _aggregate(rows: list[dict[str, Any]], ground_truth_path: Path) -> dict[str, Any]:
    overall_counts = Counter(row["outcome"] for row in rows)
    overall = classification_metrics(
        tp=overall_counts["TP"],
        fp=overall_counts["FP"],
        fn=overall_counts["FN"],
        tn=overall_counts["TN"],
    )
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["category"]].append(row)
    by_rule = {}
    for category, category_rows in sorted(grouped.items()):
        counts = Counter(row["outcome"] for row in category_rows)
        by_rule[category] = classification_metrics(
            tp=counts["TP"], fp=counts["FP"], fn=counts["FN"], tn=counts["TN"]
        )
    macro_f1 = statistics.mean(item["f1"] for item in by_rule.values()) if by_rule else 0.0
    tp_rows = [row for row in rows if row["outcome"] == "TP"]
    location = {
        "evaluated_true_positives": len(tp_rows),
        "file_level_accuracy": _boolean_mean(tp_rows, "doc_file_correct"),
        "entity_level_accuracy": _boolean_mean(tp_rows, "code_entity_correct"),
        "line_level_accuracy_tolerance_2": _boolean_mean(tp_rows, "doc_line_within_2"),
    }
    times = [row["analysis_time_ms"] for row in rows]
    performance = {
        "case_count": len(rows),
        "total_scanned_files": sum(row["scanned_files"] for row in rows),
        "average_analysis_time_ms": round(statistics.mean(times), 6) if times else 0.0,
        "median_analysis_time_ms": round(statistics.median(times), 6) if times else 0.0,
        "p95_analysis_time_ms": round(_percentile(times, 0.95), 6),
    }
    errors = [
        {
            "case_id": row["case_id"],
            "category": row["category"],
            "outcome": row["outcome"],
            "analysis": (
                "负例触发目标规则；检查规则作用域和文档实体识别。"
                if row["outcome"] == "FP"
                else "正例未触发目标规则；检查实体抽取、对齐和规则边界。"
            ),
            "possible_improvement": (
                "收紧显式证据或作用域约束。"
                if row["outcome"] == "FP"
                else "补强结构解析或保守对齐覆盖。"
            ),
        }
        for row in rows
        if row["outcome"] in {"FP", "FN"}
    ]
    return {
        "benchmark_version": BENCHMARK_VERSION,
        "ground_truth_sha256": hashlib.sha256(ground_truth_path.read_bytes()).hexdigest(),
        "method": "Rule-only (--ai off)",
        "case_count": len(rows),
        "positive_cases": sum(row["expected_finding"] for row in rows),
        "negative_cases": sum(not row["expected_finding"] for row in rows),
        "overall": {
            **overall,
            "micro_precision": overall["precision"],
            "micro_recall": overall["recall"],
            "micro_f1": overall["f1"],
            "macro_f1": round(macro_f1, 6),
        },
        "by_rule": by_rule,
        "location_accuracy": location,
        "performance": performance,
        "error_analysis": errors,
        "cases": rows,
        "ai_experiments": {
            "provider_configured": False,
            "smoke_test": "NOT RUN",
            "llm_only_baseline": "NOT RUN",
            "hybrid_benchmark": "NOT RUN",
        },
    }


def _boolean_mean(rows: list[dict[str, Any]], key: str) -> float:
    return round(sum(bool(row[key]) for row in rows) / len(rows), 6) if rows else 0.0


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def write_evaluation_outputs(
    evaluation: dict[str, Any],
    *,
    json_path: str | Path,
    csv_path: str | Path,
    markdown_path: str | Path,
) -> None:
    json_target = Path(json_path)
    csv_target = Path(csv_path)
    markdown_target = Path(markdown_path)
    for target in (json_target, csv_target, markdown_target):
        target.parent.mkdir(parents=True, exist_ok=True)
    json_target.write_text(
        json.dumps(evaluation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    fieldnames = list(evaluation["cases"][0]) if evaluation["cases"] else ["case_id"]
    with csv_target.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(evaluation["cases"])
    markdown_target.write_text(_markdown_report(evaluation), encoding="utf-8")


def _markdown_report(evaluation: dict[str, Any]) -> str:
    overall = evaluation["overall"]
    location = evaluation["location_accuracy"]
    performance = evaluation["performance"]
    lines = [
        "# Phase 5 确定性 Benchmark 报告",
        "",
        f"- Benchmark：`{evaluation['benchmark_version']}`",
        f"- Ground Truth SHA-256：`{evaluation['ground_truth_sha256']}`",
        (
            f"- 案例：{evaluation['case_count']}"
            f"（正例 {evaluation['positive_cases']} / 负例 {evaluation['negative_cases']}）"
        ),
        "",
        "## 总体指标",
        "",
        "| Method | Precision | Recall | F1 |",
        "| --- | ---: | ---: | ---: |",
        (
            f"| Rule-only | {overall['precision']:.4f} | {overall['recall']:.4f} | "
            f"{overall['f1']:.4f} |"
        ),
        "| LLM-only | NOT RUN | NOT RUN | NOT RUN |",
        "| DocSync-AI Hybrid | NOT RUN | NOT RUN | NOT RUN |",
        "",
        (
            f"TP={overall['tp']}，FP={overall['fp']}，FN={overall['fn']}，"
            f"TN={overall['tn']}，Macro F1={overall['macro_f1']:.4f}。"
        ),
        "",
        "## 分类指标",
        "",
        "| Rule | TP | FP | FN | TN | Precision | Recall | F1 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for rule_id, metrics in evaluation["by_rule"].items():
        lines.append(
            f"| {rule_id} | {metrics['tp']} | {metrics['fp']} | {metrics['fn']} | "
            f"{metrics['tn']} | {metrics['precision']:.4f} | {metrics['recall']:.4f} | "
            f"{metrics['f1']:.4f} |"
        )
    lines.extend(
        [
            "",
            "## 定位准确率",
            "",
            f"- 文档文件级：{location['file_level_accuracy']:.4f}",
            f"- 代码实体级：{location['entity_level_accuracy']:.4f}",
            f"- 文档行级（±2 行）：{location['line_level_accuracy_tolerance_2']:.4f}",
            "",
            "## 性能",
            "",
            f"- 平均：{performance['average_analysis_time_ms']:.3f} ms/case",
            f"- 中位：{performance['median_analysis_time_ms']:.3f} ms/case",
            f"- P95：{performance['p95_analysis_time_ms']:.3f} ms/case",
            f"- 处理文件：{performance['total_scanned_files']}",
            "",
            "## 错误分析",
            "",
        ]
    )
    if evaluation["error_analysis"]:
        for error in evaluation["error_analysis"]:
            lines.append(
                f"- `{error['case_id']}` / {error['category']} / {error['outcome']}："
                f"{error['analysis']} 改进方向：{error['possible_improvement']}"
            )
    else:
        lines.append(
            "本版本 controlled benchmark 未出现 FP 或 FN；这不代表对所有真实项目均达到相同表现。"
        )
    lines.extend(
        [
            "",
            "## AI 实验状态",
            "",
            (
                "真实 Provider 未配置时，LLM-only 与 Hybrid AI Benchmark "
                "必须保持 `NOT RUN`，不填入模拟数值。"
            ),
            "",
        ]
    )
    return "\n".join(lines)


def write_svg_charts(evaluation: dict[str, Any], charts_dir: str | Path) -> list[Path]:
    directory = Path(charts_dir)
    directory.mkdir(parents=True, exist_ok=True)
    overall_path = directory / "Phase5_总体指标_20260916_v01.svg"
    rules_path = directory / "Phase5_DS001至DS005分类F1_20260916_v01.svg"
    _write_bar_svg(
        overall_path,
        "Rule-only 总体指标",
        [
            ("Precision", evaluation["overall"]["precision"]),
            ("Recall", evaluation["overall"]["recall"]),
            ("F1", evaluation["overall"]["f1"]),
        ],
    )
    _write_bar_svg(
        rules_path,
        "DS001–DS005 分类 F1",
        [(rule, metrics["f1"]) for rule, metrics in evaluation["by_rule"].items()],
    )
    return [overall_path, rules_path]


def _write_bar_svg(path: Path, title: str, values: list[tuple[str, float]]) -> None:
    width, height = 760, 420
    chart_left, baseline, max_height = 80, 340, 240
    gap = 35
    bar_width = (width - chart_left * 2 - gap * (len(values) - 1)) / max(len(values), 1)
    elements = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}">'
        ),
        '<rect width="100%" height="100%" fill="#f7f9fc"/>',
        (
            '<text x="40" y="42" font-family="Segoe UI, sans-serif" font-size="22" '
            f'font-weight="700" fill="#172033">{title}</text>'
        ),
        (
            f'<line x1="{chart_left}" y1="{baseline}" x2="{width - chart_left}" '
            f'y2="{baseline}" stroke="#9aa8bb"/>'
        ),
    ]
    for index, (label, value) in enumerate(values):
        x = chart_left + index * (bar_width + gap)
        bar_height = max_height * value
        y = baseline - bar_height
        elements.extend(
            [
                (
                    f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width:.1f}" '
                    f'height="{bar_height:.1f}" rx="6" fill="#2864dc"/>'
                ),
                (
                    f'<text x="{x + bar_width / 2:.1f}" y="{y - 10:.1f}" '
                    'text-anchor="middle" font-family="Segoe UI, sans-serif" '
                    f'font-size="15" fill="#172033">{value:.3f}</text>'
                ),
                (
                    f'<text x="{x + bar_width / 2:.1f}" y="{baseline + 28}" '
                    'text-anchor="middle" font-family="Segoe UI, sans-serif" '
                    f'font-size="14" fill="#43506a">{label}</text>'
                ),
            ]
        )
    elements.append("</svg>")
    path.write_text("\n".join(elements) + "\n", encoding="utf-8")
