import json
from pathlib import Path

from docsync_ai.cli import main


def test_cli_analyzes_demo_and_writes_json(tmp_path):
    project_root = Path(__file__).parents[1]
    demo = project_root / "examples" / "demo_project"
    output = tmp_path / "report.json"

    exit_code = main(["analyze", str(demo), "--output", str(output)])

    assert exit_code == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["metadata"]["analyzed_code_executed"] is False
    assert report["summary"]["scanned_files"] == 3
    assert report["summary"]["confirmed_findings"] == 5
    assert report["summary"]["semantic_candidates"] == 3
    assert report["summary"]["findings"] == 5
    assert {item["rule_id"] for item in report["findings"]} == {
        "DS001",
        "DS002",
        "DS003",
        "DS004",
        "DS005",
    }
    assert len(report["semantic_candidates"]) == 3
    assert all(
        item["status"] == "NEEDS_SEMANTIC_REVIEW"
        for item in report["semantic_candidates"]
    )
    assert report["alignments"]
