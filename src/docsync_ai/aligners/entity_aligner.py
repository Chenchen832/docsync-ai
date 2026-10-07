"""Explainable deterministic alignment of code and documentation entities."""

from __future__ import annotations

import re
from pathlib import Path

from docsync_ai.aligners.normalizer import normalize_identifier, normalize_qualified_name
from docsync_ai.models import AlignmentCandidate, CodeEntity, DocEntity


class EntityAligner:
    """Align entities using fixed evidence tiers rather than learned weights."""

    def align(
        self, code_entities: list[CodeEntity], doc_entities: list[DocEntity]
    ) -> list[AlignmentCandidate]:
        results: list[AlignmentCandidate] = []
        for doc in doc_entities:
            candidate = self.best_alignment(doc, code_entities)
            if candidate is not None:
                results.append(candidate)
        return results

    def best_alignment(
        self, doc_entity: DocEntity, code_entities: list[CodeEntity]
    ) -> AlignmentCandidate | None:
        compatible = [item for item in code_entities if self._compatible(item, doc_entity)]
        scored = [self._score(item, doc_entity, compatible) for item in compatible]
        scored = [item for item in scored if item is not None]
        if not scored:
            return None
        scored.sort(key=lambda item: item.alignment_score, reverse=True)
        if len(scored) > 1 and scored[0].alignment_score == scored[1].alignment_score:
            return None
        return scored[0]

    @staticmethod
    def _compatible(code: CodeEntity, doc: DocEntity) -> bool:
        if doc.entity_type == "function_call":
            return code.entity_type in {"function", "async_function", "method"}
        if doc.entity_type in {"documented_parameter", "declared_default"}:
            return code.entity_type in {"function", "async_function", "method", "cli_argument"}
        if doc.entity_type == "cli_argument":
            return code.entity_type == "cli_argument"
        if doc.entity_type == "config_key":
            return code.entity_type == "config_key"
        return False

    def _score(
        self,
        code: CodeEntity,
        doc: DocEntity,
        compatible: list[CodeEntity],
    ) -> AlignmentCandidate | None:
        code_name = code.name
        doc_name = doc.name.rsplit(".", 1)[-1]
        if doc.name.strip() == code.qualified_name.strip():
            return self._candidate(
                code, doc, "exact_qualified_name", 1.0, ["qualified names match exactly"]
            )
        if doc.name.strip().casefold() == code.qualified_name.strip().casefold():
            return self._candidate(
                code,
                doc,
                "case_normalized_qualified_name",
                0.90,
                ["qualified names match after case normalization"],
            )

        if doc.entity_type == "function_call":
            exact = [item for item in compatible if item.name == doc_name]
            if code.name == doc_name and len(exact) == 1:
                return self._candidate(
                    code, doc, "exact_name", 0.95, ["unique function name match"]
                )
            normalized = [
                item
                for item in compatible
                if normalize_identifier(item.name) == normalize_identifier(doc_name)
            ]
            if (
                normalize_identifier(code.name) == normalize_identifier(doc_name)
                and len(normalized) == 1
            ):
                return self._candidate(
                    code, doc, "normalized_name", 0.90, ["unique case/hyphen normalized name match"]
                )

        if doc.entity_type == "cli_argument":
            normalized = [
                item
                for item in compatible
                if normalize_identifier(item.name) == normalize_identifier(doc.name)
            ]
            if (
                normalize_identifier(code.name) == normalize_identifier(doc.name)
                and len(normalized) == 1
            ):
                return self._candidate(
                    code,
                    doc,
                    "normalized_cli_name",
                    0.95,
                    ["CLI names match after --/hyphen/underscore normalization"],
                )

        if doc.entity_type == "declared_default" and code.entity_type == "cli_argument":
            if normalize_identifier(code.name) == normalize_identifier(doc.name):
                return self._candidate(
                    code,
                    doc,
                    "normalized_cli_name",
                    0.95,
                    ["declared CLI option matches after --/hyphen/underscore normalization"],
                )

        if doc.entity_type == "config_key":
            normalized = [
                item
                for item in compatible
                if normalize_qualified_name(item.qualified_name)
                == normalize_qualified_name(doc.name)
            ]
            if (
                normalize_qualified_name(code.qualified_name) == normalize_qualified_name(doc.name)
                and len(normalized) == 1
            ):
                return self._candidate(
                    code,
                    doc,
                    "normalized_config_path",
                    0.95,
                    ["nested config paths match after normalization"],
                )

        context = normalize_identifier(str(doc.metadata.get("context_heading", "")))
        if context and normalize_identifier(code.name) in re.split(r"[^a-z0-9_]+", context):
            same_name = [item for item in compatible if item.name == code.name]
            if len(same_name) == 1:
                return self._candidate(
                    code,
                    doc,
                    "heading_context",
                    0.90,
                    ["documentation heading names a unique code entity"],
                )

        doc_stem = normalize_identifier(Path(doc.file_path).stem)
        code_stem = normalize_identifier(Path(code.file_path).stem)
        if doc_stem == code_stem and normalize_identifier(code_name) == normalize_identifier(
            doc_name
        ):
            return self._candidate(
                code,
                doc,
                "file_and_name_context",
                0.85,
                ["file/module stem and normalized name match"],
            )
        return None

    @staticmethod
    def _candidate(
        code: CodeEntity,
        doc: DocEntity,
        alignment_type: str,
        score: float,
        evidence: list[str],
    ) -> AlignmentCandidate:
        return AlignmentCandidate(
            code_entity=code,
            doc_entity=doc,
            alignment_type=alignment_type,
            alignment_score=score,
            evidence=evidence,
        )
