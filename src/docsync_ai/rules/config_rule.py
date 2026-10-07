"""DS004: deterministic configuration-key drift detection."""

from __future__ import annotations

from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

from docsync_ai.aligners import EntityAligner, normalize_qualified_name
from docsync_ai.models import CodeEntity, DocEntity, Finding, FindingStatus
from docsync_ai.scoring import ConfidenceScorer


class ConfigKeyRule:
    rule_id = "DS004"
    issue_type = "CONFIG_KEY_MISMATCH"

    def check(
        self, code_entities: list[CodeEntity], doc_entities: list[DocEntity]
    ) -> list[Finding]:
        config_keys = [item for item in code_entities if item.entity_type == "config_key"]
        documented = [
            item
            for item in doc_entities
            if item.entity_type == "config_key"
            and item.metadata.get("source_kind") == "fenced_config_block"
        ]
        if not config_keys:
            return []

        by_file: dict[str, list[CodeEntity]] = defaultdict(list)
        for entity in config_keys:
            by_file[entity.file_path].append(entity)
        aligner = EntityAligner()
        scorer = ConfidenceScorer()
        findings: list[Finding] = []
        for doc in documented:
            if aligner.best_alignment(doc, config_keys) is not None:
                continue
            scoped, alignment_type, alignment_score, evidence = self._scope(doc, by_file)
            if not scoped:
                continue
            status = (
                FindingStatus.CONFIRMED
                if alignment_type != "ambiguous_config_scope"
                else FindingStatus.NEEDS_SEMANTIC_REVIEW
            )
            evidence_type = (
                "explicit_config_block" if status == FindingStatus.CONFIRMED else "ambiguous_scope"
            )
            assessment = scorer.assess(
                alignment_score=alignment_score,
                evidence_type=evidence_type,
                status=status,
            )
            nearest = self._nearest(doc.name, scoped)
            findings.append(
                Finding(
                    rule_id=self.rule_id,
                    issue_type=self.issue_type,
                    severity="HIGH" if status == FindingStatus.CONFIRMED else "MEDIUM",
                    confidence=assessment.score,
                    code_location=nearest.location,
                    doc_location=doc.location,
                    code_fact={
                        "available_keys": sorted({item.qualified_name for item in scoped}),
                        "nearest_key": nearest.qualified_name,
                    },
                    doc_fact={"documented_key": doc.name, "value": doc.metadata.get("value")},
                    message=f"文档配置块使用键 `{doc.name}`，但选定配置文件中不存在该路径。",
                    suggestion=f"核对配置键；最接近的实际路径为 `{nearest.qualified_name}`。",
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
        by_file: dict[str, list[CodeEntity]],
    ) -> tuple[list[CodeEntity], str, float, list[str]]:
        if len(by_file) == 1:
            return (
                next(iter(by_file.values())),
                "unique_config_file",
                0.95,
                ["repository contains one config file"],
            )
        context = str(doc.metadata.get("context_heading", ""))
        contextual = [
            entities
            for file_path, entities in by_file.items()
            if Path(file_path).stem.casefold() in context.casefold()
        ]
        if len(contextual) == 1:
            return (
                contextual[0],
                "config_heading_file",
                0.90,
                ["heading identifies one config file"],
            )
        return (
            [item for entities in by_file.values() for item in entities],
            "ambiguous_config_scope",
            0.75,
            ["multiple config files remain"],
        )

    @staticmethod
    def _nearest(name: str, keys: list[CodeEntity]) -> CodeEntity:
        normalized = normalize_qualified_name(name)
        return max(
            keys,
            key=lambda item: SequenceMatcher(
                None, normalized, normalize_qualified_name(item.qualified_name)
            ).ratio(),
        )


def check_config_key_consistency(
    code_entities: list[CodeEntity], doc_entities: list[DocEntity]
) -> list[Finding]:
    return ConfigKeyRule().check(code_entities, doc_entities)
