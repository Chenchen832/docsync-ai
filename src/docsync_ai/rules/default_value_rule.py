"""Default-value consistency rule."""

from __future__ import annotations

import json
from typing import Any

from docsync_ai.aligners import EntityAligner, normalize_identifier
from docsync_ai.models import CodeEntity, DocEntity, Finding, FindingStatus
from docsync_ai.scoring import ConfidenceScorer


def _normalized(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _normalized_doc_value(value: Any, raw_value: str) -> Any:
    """Normalize only unquoted, explicit boolean/None documentation literals."""

    raw = raw_value.strip()
    if isinstance(value, str) and not raw.startswith(("'", '"')):
        lowered = value.casefold()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
        if lowered in {"none", "null"}:
            return None
    return value


class DefaultValueRule:
    rule_id = "DS002"
    issue_type = "DEFAULT_VALUE_MISMATCH"

    def check(
        self, code_entities: list[CodeEntity], doc_entities: list[DocEntity]
    ) -> list[Finding]:
        claims = [entity for entity in doc_entities if entity.entity_type == "declared_default"]
        findings: list[Finding] = []
        aligner = EntityAligner()
        scorer = ConfidenceScorer()
        for claim in claims:
            parameter = str(claim.metadata.get("parameter_name", claim.name))
            raw_value = str(claim.metadata.get("raw_value", ""))
            doc_default = _normalized_doc_value(claim.metadata.get("default_value"), raw_value)
            candidates = self._candidates(parameter, claim, code_entities)
            if len(candidates) != 1:
                continue
            entity, key = candidates[0]
            code_default = entity.default_values[key]
            if _normalized(code_default) == _normalized(doc_default):
                continue
            alignment = aligner.best_alignment(claim, [entity])
            if alignment is None:
                alignment_type = "unique_parameter_owner"
                alignment_score = 0.85
                alignment_evidence = ["only one code entity owns the declared default parameter"]
            else:
                alignment_type = alignment.alignment_type
                alignment_score = alignment.alignment_score
                alignment_evidence = alignment.evidence
            assessment = scorer.assess(
                alignment_score=alignment_score,
                evidence_type="explicit_default_declaration",
                status=FindingStatus.CONFIRMED,
            )
            findings.append(
                Finding(
                    rule_id=self.rule_id,
                    issue_type=self.issue_type,
                    severity="MEDIUM",
                    confidence=assessment.score,
                    code_location=entity.location,
                    doc_location=claim.location,
                    code_fact={
                        "entity": entity.qualified_name,
                        "parameter": key,
                        "default_value": code_default,
                    },
                    doc_fact={
                        "parameter": parameter,
                        "default_value": doc_default,
                        "raw_value": raw_value,
                        "text": claim.text,
                    },
                    message=(
                        f"代码中 `{key}` 的默认值为 {code_default!r}，文档声明为 {doc_default!r}。"
                    ),
                    suggestion=f"将文档中的默认值更新为 `{code_default!r}`。",
                    status=FindingStatus.CONFIRMED,
                    metadata={
                        "code_entity": entity.qualified_name,
                        "doc_context": claim.metadata.get("context_heading", ""),
                        "requires_semantic_review": False,
                        "alignment_type": alignment_type,
                        "alignment_score": alignment_score,
                        "alignment_evidence": alignment_evidence,
                        "confidence_evidence": assessment.factors,
                    },
                )
            )
        return findings

    @staticmethod
    def _candidates(
        parameter: str, claim: DocEntity, code_entities: list[CodeEntity]
    ) -> list[tuple[CodeEntity, str]]:
        if parameter.startswith("--"):
            return [
                (entity, entity.name)
                for entity in code_entities
                if entity.entity_type == "cli_argument"
                and normalize_identifier(entity.name) == normalize_identifier(parameter)
                and entity.name in entity.default_values
            ]

        candidates = [
            (entity, parameter)
            for entity in code_entities
            if entity.entity_type in {"function", "async_function", "method"}
            and parameter in entity.default_values
        ]
        if len(candidates) <= 1:
            return candidates

        context = str(claim.metadata.get("context_heading", "")).casefold()
        contextual = [item for item in candidates if item[0].name.casefold() in context]
        return contextual if contextual else []


def check_default_value_consistency(
    code_entities: list[CodeEntity], doc_entities: list[DocEntity]
) -> list[Finding]:
    return DefaultValueRule().check(code_entities, doc_entities)
