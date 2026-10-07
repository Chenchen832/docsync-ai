import json
from pathlib import Path

from docsync_ai.cli import analyze_project, main
from docsync_ai.semantic import MockLLMProvider


def _demo_path():
    return Path(__file__).parents[1] / "examples" / "demo_project"


def test_ai_off_does_not_call_supplied_provider(tmp_path):
    provider = MockLLMProvider(["INCONSISTENT"])
    report = analyze_project(
        _demo_path(), ai_mode="off", provider=provider, cache_path=tmp_path / "cache.json"
    )

    assert provider.call_count == 0
    assert report["ai_statistics"]["enabled"] is False
    assert report["summary"]["confirmed_findings"] == 5
    assert report["summary"]["semantic_candidates"] == 3


def test_ai_review_mock_demonstrates_all_three_outcomes(tmp_path):
    provider = MockLLMProvider(["CONSISTENT", "INCONSISTENT", "UNCERTAIN"])
    report = analyze_project(
        _demo_path(), ai_mode="review", provider=provider, cache_path=tmp_path / "cache.json"
    )

    assert report["summary"]["confirmed_findings"] == 6
    assert report["summary"]["semantic_candidates"] == 1
    assert len(report["semantic_reviews"]) == 3
    assert {item["decision"] for item in report["semantic_reviews"]} == {
        "CONSISTENT",
        "INCONSISTENT",
        "UNCERTAIN",
    }
    assert report["ai_statistics"]["successful_reviews"] == 3
    assert sum(item["source"] == "AI_SEMANTIC_REVIEW" for item in report["findings"]) == 1


def test_missing_api_configuration_preserves_deterministic_results(tmp_path, monkeypatch):
    for name in ("DOCSYNC_AI_API_KEY", "DOCSYNC_AI_BASE_URL", "DOCSYNC_AI_MODEL"):
        monkeypatch.delenv(name, raising=False)

    report = analyze_project(
        _demo_path(), ai_mode="review", cache_path=tmp_path / "cache.json"
    )

    assert report["summary"]["confirmed_findings"] == 5
    assert report["summary"]["semantic_candidates"] == 3
    assert report["ai_statistics"]["failed_reviews"] == 3
    assert all(item["status"] == "NEEDS_MANUAL_REVIEW" for item in report["semantic_candidates"])


def test_cli_mock_ai_mode_writes_schema_v3_report(tmp_path):
    output = tmp_path / "phase3.json"
    cache = tmp_path / "cache.json"
    exit_code = main(
        [
            "analyze",
            str(_demo_path()),
            "--ai",
            "review",
            "--ai-provider",
            "mock",
            "--ai-cache",
            str(cache),
            "--output",
            str(output),
        ]
    )

    report = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert report["schema_version"] == "3.0"
    assert "semantic_reviews" in report
    assert "ai_statistics" in report


def test_invalid_ai_threshold_returns_cli_error(tmp_path):
    output = tmp_path / "phase3.json"
    exit_code = main(
        [
            "analyze",
            str(_demo_path()),
            "--ai",
            "review",
            "--ai-provider",
            "mock",
            "--semantic-threshold",
            "1.5",
            "--output",
            str(output),
        ]
    )

    assert exit_code == 2
    assert not output.exists()
