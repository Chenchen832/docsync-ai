"""DS005: static call-signature validation for fenced Python examples."""

from __future__ import annotations

from docsync_ai.aligners import EntityAligner
from docsync_ai.models import CodeEntity, DocEntity, Finding, FindingStatus
from docsync_ai.scoring import ConfidenceScorer


class CallSignatureRule:
    rule_id = "DS005"
    issue_type = "CALL_SIGNATURE_MISMATCH"

    def check(
        self, code_entities: list[CodeEntity], doc_entities: list[DocEntity]
    ) -> list[Finding]:
        functions = [
            item
            for item in code_entities
            if item.entity_type in {"function", "async_function", "method"}
        ]
        calls = [item for item in doc_entities if item.entity_type == "function_call"]
        aligner = EntityAligner()
        scorer = ConfidenceScorer()
        findings: list[Finding] = []
        for call in calls:
            alignment = aligner.best_alignment(call, functions)
            if alignment is None:
                continue
            if call.metadata.get("has_starred_arguments") or call.metadata.get(
                "has_keyword_unpacking"
            ):
                continue
            function = alignment.code_entity
            problems = self._problems(function, call)
            if not problems:
                continue
            assessment = scorer.assess(
                alignment_score=alignment.alignment_score,
                evidence_type="invalid_call_signature",
                status=FindingStatus.CONFIRMED,
            )
            findings.append(
                Finding(
                    rule_id=self.rule_id,
                    issue_type=self.issue_type,
                    severity="HIGH",
                    confidence=assessment.score,
                    code_location=function.location,
                    doc_location=call.location,
                    code_fact={
                        "entity": function.qualified_name,
                        "parameters": function.parameters,
                        "default_values": function.default_values,
                    },
                    doc_fact={"call": call.code_snippet, "problems": problems},
                    message=f"文档调用 `{call.code_snippet}` 与当前函数签名不兼容。",
                    suggestion="补充必需参数，或按当前函数签名调整示例调用。",
                    status=FindingStatus.CONFIRMED,
                    metadata={
                        "requires_semantic_review": False,
                        "alignment_type": alignment.alignment_type,
                        "alignment_score": alignment.alignment_score,
                        "alignment_evidence": alignment.evidence,
                        "confidence_evidence": assessment.factors,
                    },
                )
            )
        return findings

    @staticmethod
    def _problems(function: CodeEntity, call: DocEntity) -> list[dict[str, object]]:
        kinds = function.metadata.get("parameter_kinds", {})
        parameters = [
            item.lstrip("*")
            for item in function.parameters
            if item.lstrip("*") not in {"self", "cls"}
        ]
        positional_parameters = [
            item
            for item in parameters
            if kinds.get(item) in {"positional_only", "positional_or_keyword"}
        ]
        required = {
            item
            for item in parameters
            if kinds.get(item) not in {"var_positional", "var_keyword"}
            and item not in function.default_values
        }
        arguments = call.metadata.get("arguments", [])
        positional_count = sum(item.get("kind") == "positional" for item in arguments)
        keyword_names = {
            str(item.get("name"))
            for item in arguments
            if item.get("kind") == "keyword" and item.get("name") != "**"
        }
        accepts_varargs = any(kinds.get(item) == "var_positional" for item in parameters)
        accepts_kwargs = any(kinds.get(item) == "var_keyword" for item in parameters)
        positional_only = {item for item in parameters if kinds.get(item) == "positional_only"}

        # DS001 owns unknown/positional-only keyword errors; avoid duplicate findings.
        if (
            keyword_names - set(parameters) and not accepts_kwargs
        ) or keyword_names & positional_only:
            return []

        problems: list[dict[str, object]] = []
        if positional_count > len(positional_parameters) and not accepts_varargs:
            problems.append(
                {
                    "type": "too_many_positional_arguments",
                    "provided": positional_count,
                    "maximum": len(positional_parameters),
                }
            )
        assigned_by_position = set(positional_parameters[:positional_count])
        duplicates = assigned_by_position & keyword_names
        if duplicates:
            problems.append({"type": "multiple_values", "parameters": sorted(duplicates)})
        assigned = assigned_by_position | keyword_names
        missing = sorted(required - assigned)
        if missing:
            problems.append({"type": "missing_required_arguments", "parameters": missing})
        return problems


def check_call_signature_consistency(
    code_entities: list[CodeEntity], doc_entities: list[DocEntity]
) -> list[Finding]:
    return CallSignatureRule().check(code_entities, doc_entities)
