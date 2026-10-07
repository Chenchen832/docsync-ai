"""Command-line runner for generating and evaluating benchmark-v1."""

from __future__ import annotations

import argparse
from pathlib import Path

from docsync_ai.benchmark.evaluator import (
    evaluate_benchmark,
    generate_benchmark,
    write_evaluation_outputs,
    write_svg_charts,
)

DEFAULT_BENCHMARK_ROOT = Path(r"D:\AI+开源主题赛\03_测试与评测\benchmark")
DEFAULT_RESULTS_ROOT = Path(r"D:\AI+开源主题赛\03_测试与评测\测试结果")
DEFAULT_CHARTS_ROOT = Path(r"D:\AI+开源主题赛\03_测试与评测\实验图表")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate and evaluate DocSync-AI benchmark-v1")
    parser.add_argument("--benchmark-root", type=Path, default=DEFAULT_BENCHMARK_ROOT)
    parser.add_argument("--results-root", type=Path, default=DEFAULT_RESULTS_ROOT)
    parser.add_argument("--charts-root", type=Path, default=DEFAULT_CHARTS_ROOT)
    args = parser.parse_args()

    generated = generate_benchmark(args.benchmark_root)
    evaluation = evaluate_benchmark(args.benchmark_root)
    prefix = args.results_root / "Phase5_确定性Benchmark_20260916_v01"
    write_evaluation_outputs(
        evaluation,
        json_path=prefix.with_suffix(".json"),
        csv_path=prefix.with_suffix(".csv"),
        markdown_path=args.results_root / "Phase5_确定性Benchmark报告_20260916_v01.md",
    )
    write_svg_charts(evaluation, args.charts_root)
    print(
        f"Generated {generated['deterministic_cases']} deterministic and "
        f"{generated['semantic_cases']} semantic cases; "
        f"F1={evaluation['overall']['f1']:.4f}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
