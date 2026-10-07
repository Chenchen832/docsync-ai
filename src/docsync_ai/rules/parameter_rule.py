"""Function and method parameter consistency rule."""

from __future__ import annotations

from docsync_ai.aligners import EntityAligner
from docsync_ai.models import CodeEntity, DocEntity, Finding, FindingStatus
from docsync_ai.scoring import ConfidenceScorer


def _plain_parameter(name: str) -> str:
    return name.lstrip("*")


class ParameterRule:
    """Detect explicit interface-name drift, never caller-local variable names."""

    rule_id = "DS001"
    issue_type = "PARAMETER_NAME_MISMATCH"

    def check(
        self, code_entities: list[CodeEntity], doc_entities: list[DocEntity]
    ) -> list[Finding]:
        functions = [
            entity
            for entity in code_entities
            if entity.entity_type in {"function", "async_function", "method"}
        ]
        findings: list[Finding] = []
        aligner = EntityAligner()
        scorer = ConfidenceScorer()

        calls = [entity for entity in doc_entities if entity.entity_type == "function_call"]
        for call in calls:
            alignment = aligner.best_alignment(call, functions)
            if alignment is None:
                continue
            function = alignment.code_entity
            code_parameters = [
                _plain_parameter(item)
                for item in function.parameters
                if _plain_parameter(item) not in {"self", "cls"}
            ]
            accepts_arbitrary_keywords = any(item.startswith("**") for item in function.parameters)
            positional_only = {
                name
                for name, kind in function.metadata.get("parameter_kinds", {}).items()
                if kind == "positional_only"
            }

            # Positional argument expressions are values. An expression such as
            # ``train(local_path)`` says nothing about the callee's parameter name.
            for name in call.metadata.get("keyword_parameters", []):
                documented_name = str(name)
                valid_keyword = (
                    documented_name in code_parameters and documented_name not in positional_only
                )
                if valid_keyword or accepts_arbitrary_keywords:
                    continue
                findings.append(
                    self._call_finding(
                        function=function,
                        call=call,
                        documented_name=documented_name,
                        positional_only=documented_name in positional_only,
                        alignment_type=alignment.alignment_type,
                        alignment_score=alignment.alignment_score,
                        alignment_evidence=alignment.evidence,
                        scorer=scorer,
                    )
                )

        declarations = [
            entity for entity in doc_entities if entity.entity_type == "documented_parameter"
        ]
        for declaration in declarations:
            alignment = aligner.best_alignment(declaration, functions)
            if alignment is None:
                function = self._function_for_declaration(declaration, functions)
                if function is None:
                    continue
                alignment_type = "unique_weak_context"
                alignment_score = 0.70
                alignment_evidence = [
                    "only one compatible function; parameter meaning is unresolved"
                ]
            else:
                function = alignment.code_entity
                alignment_type = alignment.alignment_type
                alignment_score = alignment.alignment_score
                alignment_evidence = alignment.evidence
            code_parameters = {
                _plain_parameter(item)
                for item in function.parameters
                if _plain_parameter(item) not in {"self", "cls"}
            }
            documented_name = declaration.name
            if documented_name in code_parameters or any(
                item.startswith("**") for item in function.parameters
            ):
                continue
            assessment = scorer.assess(
                alignment_score=alignment_score,
                evidence_type="parameter_declaration_candidate",
                status=FindingStatus.NEEDS_SEMANTIC_REVIEW,
            )
            findings.append(
                Finding(
                    rule_id=self.rule_id,
                    issue_type=self.issue_type,
                    severity="MEDIUM",
                    confidence=assessment.score,
                    code_location=function.location,
                    doc_location=declaration.location,
                    code_fact={
                        "entity": function.qualified_name,
                        "parameters": sorted(code_parameters),
                    },
                    doc_fact={
                        "documented_parameter": documented_name,
                        "text": declaration.text,
                        "declaration_kind": "parameter_list",
                    },
                    message=(
                        f"文档参数表声明 `{documented_name}`，但该名称不在"
                        f" `{function.name}` 的当前代码签名中。"
                    ),
                    suggestion=(
                        f"核对参数表中的 `{documented_name}`，并将其更新为当前代码签名中的名称。"
                    ),
                    status=FindingStatus.NEEDS_SEMANTIC_REVIEW,
                    metadata={
                        "code_entity": function.qualified_name,
                        "doc_entity": declaration.name,
                        "requires_semantic_review": True,
                        "alignment_type": alignment_type,
                        "alignment_score": alignment_score,
                        "alignment_evidence": alignment_evidence,
                        "confidence_evidence": assessment.factors,
                    },
                )
            )
        return findings

    def _call_finding(
        self,
        *,
        function: CodeEntity,
        call: DocEntity,
        documented_name: str,
        positional_only: bool,
        alignment_type: str,
        alignment_score: float,
        alignment_evidence: list[str],
        scorer: ConfidenceScorer,
    ) -> Finding:
        code_parameters = [
            _plain_parameter(item)
            for item in function.parameters
            if _plain_parameter(item) not in {"self", "cls"}
        ]
        reason = (
            "该形参仅允许按位置传递，不能作为关键字参数使用。"
            if positional_only
            else "该关键字参数不在当前代码签名中。"
        )
        assessment = scorer.assess(
            alignment_score=alignment_score,
            evidence_type="invalid_keyword_argument",
            status=FindingStatus.CONFIRMED,
        )
        return Finding(
            rule_id=self.rule_id,
            issue_type=self.issue_type,
            severity="HIGH",
            confidence=assessment.score,
            code_location=function.location,
            doc_location=call.location,
            code_fact={
                "entity": function.qualified_name,
                "parameters": code_parameters,
            },
            doc_fact={
                "call": call.code_snippet,
                "documented_parameter": documented_name,
                "argument_kind": "keyword",
            },
            message=f"文档调用 `{call.name}` 使用关键字参数 `{documented_name}`；{reason}",
            suggestion=f"删除或更正文档中的关键字参数 `{documented_name}`。",
            status=FindingStatus.CONFIRMED,
            metadata={
                "code_entity": function.qualified_name,
                "doc_entity": call.name,
                "requires_semantic_review": False,
                "alignment_type": alignment_type,
                "alignment_score": alignment_score,
                "alignment_evidence": alignment_evidence,
                "confidence_evidence": assessment.factors,
            },
        )

    @staticmethod
    def _function_for_declaration(
        declaration: DocEntity, functions: list[CodeEntity]
    ) -> CodeEntity | None:
        context = str(declaration.metadata.get("context_heading", "")).casefold()
        contextual = [item for item in functions if item.name.casefold() in context]
        if len(contextual) == 1:
            return contextual[0]
        if len(functions) == 1:
            return functions[0]
        return None


def check_parameter_consistency(
    code_entities: list[CodeEntity], doc_entities: list[DocEntity]
) -> list[Finding]:
    return ParameterRule().check(code_entities, doc_entities)
