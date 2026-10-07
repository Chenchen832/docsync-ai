from pathlib import Path

import pytest

from docsync_ai import cli
from docsync_ai.reports import MarkdownReporter
from docsync_ai.services import analyze_project


def test_cli_and_web_core_import_the_same_analysis_service():
    assert cli.analyze_project is analyze_project


def test_analysis_service_adds_file_type_statistics():
    demo = Path(__file__).parents[1] / "examples" / "demo_project"

    report = analyze_project(demo)

    assert report["summary"]["python_files"] == 1
    assert report["summary"]["markdown_files"] == 1
    assert report["summary"]["config_files"] == 1


def test_analysis_service_warns_when_python_and_markdown_are_missing(tmp_path):
    (tmp_path / "config.json").write_text('{"enabled": true}', encoding="utf-8")

    report = analyze_project(tmp_path)

    assert len(report["analysis_warnings"]) == 2
    assert report["summary"]["python_files"] == 0
    assert report["summary"]["markdown_files"] == 0


def test_analysis_service_distinguishes_file_from_directory(tmp_path):
    file_path = tmp_path / "project.py"
    file_path.write_text("pass\n", encoding="utf-8")

    with pytest.raises(ValueError, match="not a directory"):
        analyze_project(file_path)


def test_markdown_report_contains_summary_findings_and_suggestions():
    demo = Path(__file__).parents[1] / "examples" / "demo_project"
    content = MarkdownReporter().dumps(analyze_project(demo))

    assert "# DocSync-AI 检测报告" in content
    assert "Confirmed Findings：5" in content
    assert "DS001 参数名称不一致" in content
    assert "DS005 文档中的函数调用方式已经失效" in content
    assert "修复建议" in content


def test_markdown_report_includes_ai_review_result(tmp_path):
    from docsync_ai.semantic import MockLLMProvider

    demo = Path(__file__).parents[1] / "examples" / "demo_project"
    report = analyze_project(
        demo,
        ai_mode="review",
        provider=MockLLMProvider(["CONSISTENT", "INCONSISTENT", "UNCERTAIN"]),
        cache_path=tmp_path / "cache.json",
    )

    content = MarkdownReporter().dumps(report)

    assert "## AI 语义复核" in content
    assert "RESOLVED_CONSISTENT" in content
    assert "NEEDS_MANUAL_REVIEW" in content
