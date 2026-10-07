"""Strict, provider-neutral schemas for semantic review."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from docsync_ai.models import Finding


class SchemaValidationError(ValueError):
    """Raised when a provider response violates the semantic review schema."""


class SemanticDecision(StrEnum):
    CONSISTENT = "CONSISTENT"
    INCONSISTENT = "INCONSISTENT"
    UNCERTAIN = "UNCERTAIN"


@dataclass(frozen=True, slots=True)
class SemanticReviewResult:
    decision: SemanticDecision
    confidence: float
    reason: str
    matched_concept: str
    recommended_fix: str
    evidence_summary: str = ""

    @classmethod
    def from_json(cls, content: str) -> SemanticReviewResult:
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, TypeError) as exc:
            raise SchemaValidationError("Provider returned invalid JSON") from exc
        return cls.from_mapping(data)

    @classmethod
    def from_mapping(cls, data: Any) -> SemanticReviewResult:
        if not isinstance(data, dict):
            raise SchemaValidationError("Semantic review response must be a JSON object")
        required = {"decision", "confidence", "reason", "matched_concept", "recommended_fix"}
        allowed = required | {"evidence_summary"}
        missing = required - set(data)
        unknown = set(data) - allowed
        if missing:
            raise SchemaValidationError(f"Missing fields: {sorted(missing)}")
        if unknown:
            raise SchemaValidationError(f"Unknown fields: {sorted(unknown)}")
        try:
            decision = SemanticDecision(data["decision"])
        except (ValueError, TypeError) as exc:
            raise SchemaValidationError("Invalid decision") from exc
        confidence = data["confidence"]
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise SchemaValidationError("confidence must be a number")
        confidence = float(confidence)
        if not 0.0 <= confidence <= 1.0:
            raise SchemaValidationError("confidence must be between 0.0 and 1.0")
        string_fields = {
            name: data.get(name, "")
            for name in ("reason", "matched_concept", "recommended_fix", "evidence_summary")
        }
        if any(not isinstance(value, str) for value in string_fields.values()):
            raise SchemaValidationError("Text fields must be strings")
        if not string_fields["reason"].strip():
            raise SchemaValidationError("reason must not be empty")
        return cls(decision=decision, confidence=confidence, **string_fields)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["decision"] = self.decision.value
        return data


@dataclass(frozen=True, slots=True)
class SemanticReviewRequest:
    candidate_id: str
    candidate: Finding
    payload: dict[str, Any]
    system_prompt: str
    user_prompt: str


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    content: str
    latency_ms: float
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(slots=True)
class SemanticReviewRecord:
    candidate_id: str
    provider: str
    model: str
    decision: str
    confidence: float | None
    reason: str
    final_status: str
    matched_concept: str = ""
    recommended_fix: str = ""
    evidence_summary: str = ""
    latency_ms: float = 0.0
    cache_hit: bool = False
    attempts: int = 0
    error: str | None = None
    candidate_snapshot: dict[str, Any] = field(default_factory=dict)
    policy_version: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AIStatistics:
    enabled: bool
    provider: str | None
    model: str | None
    candidate_count: int = 0
    reviewed_count: int = 0
    successful_reviews: int = 0
    failed_reviews: int = 0
    cache_hits: int = 0
    average_latency_ms: float = 0.0
    input_tokens: int | None = None
    output_tokens: int | None = None
    policy_version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SemanticReviewOutcome:
    promoted_findings: list[Finding]
    remaining_candidates: list[Finding]
    reviews: list[SemanticReviewRecord]
    statistics: AIStatistics
