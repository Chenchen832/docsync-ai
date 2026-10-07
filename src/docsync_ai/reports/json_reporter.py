"""JSON report generation."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from docsync_ai.models import AlignmentCandidate, CodeEntity, DocEntity, Finding, FindingStatus
from docsync_ai.semantic.schemas import AIStatistics, SemanticReviewRecord


class JsonReporter:
    schema_version = "3.0"

    def build(
        self,
        findings: list[Finding],
        *,
        code_entities: list[CodeEntity],
        doc_entities: list[DocEntity],
        scanned_files: list[str],
        project_root: str,
        alignments: list[AlignmentCandidate] | None = None,
        semantic_reviews: list[SemanticReviewRecord] | None = None,
        ai_statistics: AIStatistics | None = None,
    ) -> dict[str, Any]:
        alignments = alignments or []
        semantic_reviews = semantic_reviews or []
        confirmed = [item for item in findings if item.status == FindingStatus.CONFIRMED]
        candidates = [
            item
            for item in findings
            if item.status
            in {FindingStatus.NEEDS_SEMANTIC_REVIEW, FindingStatus.NEEDS_MANUAL_REVIEW}
        ]
        ai_statistics = ai_statistics or AIStatistics(
            enabled=False,
            provider=None,
            model=None,
            candidate_count=len(candidates),
        )
        severities = Counter(item.severity for item in confirmed)
        return {
            "schema_version": self.schema_version,
            "generated_at": datetime.now(UTC).isoformat(),
            "project_root": project_root,
            "summary": {
                "scanned_files": len(scanned_files),
                "code_entities": len(code_entities),
                "doc_entities": len(doc_entities),
                "findings": len(confirmed),
                "confirmed_findings": len(confirmed),
                "semantic_candidates": len(candidates),
                "total_results": len(findings),
                "alignments": len(alignments),
                "severity": {
                    "HIGH": severities.get("HIGH", 0),
                    "MEDIUM": severities.get("MEDIUM", 0),
                    "LOW": severities.get("LOW", 0),
                },
            },
            "scanned_file_paths": scanned_files,
            "alignments": [item.to_dict() for item in alignments],
            "findings": [item.to_dict() for item in confirmed],
            "semantic_candidates": [item.to_dict() for item in candidates],
            "semantic_reviews": [item.to_dict() for item in semantic_reviews],
            "ai_statistics": ai_statistics.to_dict(),
            "metadata": {
                "analysis_mode": (
                    "static-rules-with-semantic-review"
                    if ai_statistics.enabled
                    else "static-rule-only"
                ),
                "analyzed_code_executed": False,
            },
        }

    @staticmethod
    def dumps(report: dict[str, Any], *, pretty: bool = True) -> str:
        return json.dumps(
            report,
            ensure_ascii=False,
            indent=2 if pretty else None,
            sort_keys=False,
        )

    def write(self, report: dict[str, Any], output_path: str | Path) -> Path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.dumps(report) + "\n", encoding="utf-8")
        return path
