import json
from collections import Counter

import pytest

from docsync_ai.benchmark import (
    BENCHMARK_VERSION,
    classification_metrics,
    deterministic_cases,
    evaluate_benchmark,
    semantic_cases,
)
from docsync_ai.benchmark.evaluator import (
    generate_benchmark,
    write_evaluation_outputs,
    write_svg_charts,
)


def test_deterministic_dataset_has_60_balanced_cases():
    cases = deterministic_cases()

    assert len(cases) == 60
    assert Counter(case.category for case in cases) == {
        "DS001": 12,
        "DS002": 12,
        "DS003": 12,
        "DS004": 12,
        "DS005": 12,
    }
    assert sum(case.expected_finding for case in cases) == 30


def test_each_rule_has_positive_and_negative_cases():
    grouped = {}
    for case in deterministic_cases():
        grouped.setdefault(case.category, []).append(case)

    for cases in grouped.values():
        assert sum(case.expected_finding for case in cases) == 6
        assert sum(not case.expected_finding for case in cases) == 6


def test_every_deterministic_case_records_mutation_and_expected_location():
    for case in deterministic_cases():
        assert case.mutation_type
        assert case.original_content
        assert case.modified_content
        assert case.expected_doc_file == "README.md"
        assert case.expected_code_entity


def test_semantic_dataset_has_human_labeled_boundary_cases():
    cases = semantic_cases()
    decisions = Counter(case["human_ground_truth"] for case in cases)

    assert len(cases) == 24
    assert decisions == {"CONSISTENT": 10, "INCONSISTENT": 10, "UNCERTAIN": 4}
    assert all(case["human_reason"] for case in cases)


def test_classification_metrics_are_correct():
    metrics = classification_metrics(tp=8, fp=2, fn=4, tn=6)

    assert metrics["precision"] == 0.8
    assert metrics["recall"] == 0.666667
    assert metrics["f1"] == 0.727273
    assert metrics["accuracy"] == 0.7


def test_classification_metrics_handle_empty_data():
    metrics = classification_metrics(tp=0, fp=0, fn=0, tn=0)

    assert metrics["precision"] == 0.0
    assert metrics["recall"] == 0.0
    assert metrics["f1"] == 0.0
    assert metrics["accuracy"] == 0.0


def test_generation_is_idempotent_and_ground_truth_is_versioned(tmp_path):
    first = generate_benchmark(tmp_path)
    second = generate_benchmark(tmp_path)
    payload = json.loads(
        (tmp_path / "ground_truth" / "benchmark_ground_truth.json").read_text(
            encoding="utf-8"
        )
    )

    assert first == second
    assert payload["benchmark_version"] == BENCHMARK_VERSION
    assert len(payload["deterministic_cases"]) == 60
    assert len(payload["semantic_cases"]) == 24


def test_generation_rejects_changes_to_frozen_ground_truth(tmp_path):
    generate_benchmark(tmp_path)
    ground_truth = tmp_path / "ground_truth" / "deterministic_ground_truth.json"
    ground_truth.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Frozen Ground Truth differs"):
        generate_benchmark(tmp_path)


def test_evaluator_calculates_metrics_location_and_performance(tmp_path):
    generate_benchmark(tmp_path)

    evaluation = evaluate_benchmark(tmp_path)

    assert evaluation["case_count"] == 60
    assert evaluation["overall"]["tp"] == 30
    assert evaluation["overall"]["tn"] == 30
    assert evaluation["overall"]["f1"] == 1.0
    assert evaluation["location_accuracy"]["file_level_accuracy"] == 1.0
    assert evaluation["performance"]["total_scanned_files"] > 0


def test_evaluation_outputs_json_csv_markdown_and_charts(tmp_path):
    benchmark_root = tmp_path / "benchmark"
    generate_benchmark(benchmark_root)
    evaluation = evaluate_benchmark(benchmark_root)
    json_path = tmp_path / "result.json"
    csv_path = tmp_path / "result.csv"
    markdown_path = tmp_path / "result.md"

    write_evaluation_outputs(
        evaluation,
        json_path=json_path,
        csv_path=csv_path,
        markdown_path=markdown_path,
    )
    charts = write_svg_charts(evaluation, tmp_path / "charts")

    assert json.loads(json_path.read_text(encoding="utf-8"))["case_count"] == 60
    assert "case_id,category" in csv_path.read_text(encoding="utf-8-sig")
    assert "LLM-only | NOT RUN" in markdown_path.read_text(encoding="utf-8")
    assert len(charts) == 2
    assert all(path.read_text(encoding="utf-8").startswith("<svg") for path in charts)
