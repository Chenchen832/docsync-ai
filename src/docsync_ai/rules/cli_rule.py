"""DS003: deterministic CLI option drift detection."""

from __future__ import annotations

from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

from docsync_ai.aligners import EntityAligner, normalize_identifier
from docsync_ai.models import CodeEntity, DocEntity, Finding, FindingStatus
from docsync_ai.scoring import ConfidenceScorer


class CliOptionRule:
    rule_id = "DS003"
    issue_type = "CLI_OPTION_MISMATCH"

    def check(
        self, code_entities: list[CodeEntity], doc_entities: list[DocEntity]
    ) -> list[Finding]:
        options = [item for item in code_entities if item.entity_type == "cli_argument"]
        documented = [
            item
            for item in doc_entities
            if item.entity_type == "cli_argument"
            and item.metadata.get("source_kind") == "fenced_cli_command"
        ]
        if not options:
            return []

        groups: dict[tuple[str, str, str], list[CodeEntity]] = defaultdict(list)
        for option in options:
            key = (
                option.file_path,
                str(option.metadata.get("parser_context", "")),
                str(option.metadata.get("parser_name", "")),
            )
            groups[key].append(option)

        aligner = EntityAligner()
        scorer = ConfidenceScorer()
        findings: list[Finding] = []
        for doc in documented:
            if aligner.best_alignment(doc, options) is not None:
                continue
            scoped_groups, alignment_type, alignment_score, evidence = self._scope(doc, groups)
            if not scoped_groups:
                continue
            scoped_options = [item for group in scoped_groups for item in group]
            status = (
                FindingStatus.CONFIRMED
                if len(scoped_groups) == 1
                else FindingStatus.NEEDS_SEMANTIC_REVIEW
            )
            evidence_type = (
                "explicit_cli_command" if status == FindingStatus.CONFIRMED else "ambiguous_scope"
            )
            assessment = scorer.assess(
                alignment_score=alignment_score,
                evidence_type=evidence_type,
                status=status,
            )
            nearest = self._nearest(doc.name, scoped_options)
            findings.append(
                Finding(
                    rule_id=self.rule_id,
                    issue_type=self.issue_type,
                    severity="HIGH" if status == FindingStatus.CONFIRMED else "MEDIUM",
                    confidence=assessment.score,
                    code_location=nearest.location,
                    doc_location=doc.location,
                    code_fact={
                        "available_options": sorted({item.name for item in scoped_options}),
                        "nearest_option": nearest.name,
                    },
                    doc_fact={"documented_option": doc.name, "command_fragment": doc.text},
                    message=f"文档 CLI 命令使用选项 `{doc.name}`，但选定解析器未定义该选项。",
                    suggestion=f"核对该选项；最接近的可用选项为 `{nearest.name}`。",
                    status=status,
                    metadata={
                        "requires_semantic_review": status == FindingStatus.NEEDS_SEMANTIC_REVIEW,
                        "alignment_type": alignment_type,
                        "alignment_score": alignment_score,
                        "alignment_evidence": evidence,
                        "confidence_evidence": assessment.factors,
                    },
                )
            )
        return findings

    @staticmethod
    def _scope(
        doc: DocEntity,
        groups: dict[tuple[str, str, str], list[CodeEntity]],
    ) -> tuple[list[list[CodeEntity]], str, float, list[str]]:
        all_groups = list(groups.values())
        script_name = normalize_identifier(str(doc.metadata.get("script_name", "")))
        if script_name:
            matching = [
                group
                for group in all_groups
                if normalize_identifier(Path(group[0].file_path).stem) == script_name
            ]
            if len(matching) == 1:
                return (
                    matching,
                    "cli_script_file",
                    0.95,
                    ["CLI script name selects one parser scope"],
                )
            if len(matching) > 1:
                return (
                    matching,
                    "ambiguous_cli_script",
                    0.75,
                    ["CLI script maps to multiple parser scopes"],
                )
        if len(all_groups) == 1:
            return (
                all_groups,
                "unique_cli_parser",
                0.90,
                ["repository contains one argparse parser scope"],
            )
        return all_groups, "ambiguous_cli_scope", 0.75, ["multiple argparse parser scopes remain"]

    @staticmethod
    def _nearest(name: str, options: list[CodeEntity]) -> CodeEntity:
        normalized = normalize_identifier(name)
        return max(
            options,
            key=lambda item: SequenceMatcher(
                None, normalized, normalize_identifier(item.name)
            ).ratio(),
        )


def check_cli_option_consistency(
    code_entities: list[CodeEntity], doc_entities: list[DocEntity]
) -> list[Finding]:
    return CliOptionRule().check(code_entities, doc_entities)
