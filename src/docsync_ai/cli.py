"""Command-line entry point for static DocSync-AI analysis."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from docsync_ai.reports import JsonReporter
from docsync_ai.semantic import MockLLMProvider
from docsync_ai.semantic.config import SEMANTIC_REVIEW_THRESHOLD
from docsync_ai.services import analyze_project


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="docsync-ai",
        description="Statically detect Python code and Markdown documentation drift.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    analyze = subparsers.add_parser("analyze", help="Analyze a local project directory")
    analyze.add_argument("project", help="Path to the project to analyze")
    analyze.add_argument("--output", "-o", help="Write JSON to this file instead of stdout")
    analyze.add_argument(
        "--compact", action="store_true", help="Emit compact JSON when writing to stdout"
    )
    analyze.add_argument(
        "--ai",
        choices=("off", "review"),
        default="off",
        help="Review DS001 semantic candidates with an LLM (default: off)",
    )
    analyze.add_argument(
        "--ai-provider",
        choices=("openai-compatible", "mock"),
        default="openai-compatible",
        help="Semantic review provider used when --ai review is enabled",
    )
    analyze.add_argument(
        "--ai-cache",
        help="Path to the credential-free semantic review cache",
    )
    analyze.add_argument(
        "--semantic-threshold",
        type=float,
        default=SEMANTIC_REVIEW_THRESHOLD,
        help="Minimum AI confidence for a non-UNCERTAIN decision (default: 0.80)",
    )
    analyze.add_argument(
        "--mock-decisions",
        default="CONSISTENT,INCONSISTENT,UNCERTAIN",
        help=argparse.SUPPRESS,
    )
    web = subparsers.add_parser("web", help="Start the local DocSync-AI Web interface")
    web.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    web.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    if args.command == "web":
        from docsync_ai.web.app import run_web

        run_web(host=args.host, port=args.port)
        return 0
    if args.command != "analyze":
        return 2
    try:
        provider = None
        if args.ai == "review" and args.ai_provider == "mock":
            decisions = [item.strip().upper() for item in args.mock_decisions.split(",")]
            provider = MockLLMProvider(decisions)
        report = analyze_project(
            args.project,
            ai_mode=args.ai,
            provider=provider,
            cache_path=args.ai_cache,
            semantic_threshold=args.semantic_threshold,
        )
        reporter = JsonReporter()
        if args.output:
            output = reporter.write(report, args.output).resolve()
            summary = report["summary"]
            print(
                f"Report written to {output} "
                f"({summary['confirmed_findings']} confirmed findings, "
                f"{summary['semantic_candidates']} semantic candidates, "
                f"{summary['scanned_files']} files; "
                f"AI reviews: {report['ai_statistics']['successful_reviews']} successful, "
                f"{report['ai_statistics']['failed_reviews']} failed)."
            )
        else:
            print(reporter.dumps(report, pretty=not args.compact))
    except (OSError, ValueError) as exc:
        print(f"docsync-ai: error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
