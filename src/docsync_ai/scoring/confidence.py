"""Deterministic confidence ceilings for structured rule evidence."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ConfidenceAssessment:
    score: float
    factors: list[str]


class ConfidenceScorer:
    """Use the weaker of alignment and rule evidence; no weighted randomness."""

    EVIDENCE_CEILINGS = {
        "invalid_keyword_argument": 0.99,
        "explicit_default_declaration": 0.99,
        "explicit_cli_command": 0.98,
        "explicit_config_block": 0.97,
        "invalid_call_signature": 0.99,
        "parameter_declaration_candidate": 0.85,
        "ambiguous_scope": 0.75,
    }

    def assess(
        self,
        *,
        alignment_score: float,
        evidence_type: str,
        status: str,
    ) -> ConfidenceAssessment:
        if evidence_type not in self.EVIDENCE_CEILINGS:
            raise ValueError(f"Unknown evidence type: {evidence_type}")
        evidence_ceiling = self.EVIDENCE_CEILINGS[evidence_type]
        score = round(min(max(alignment_score, 0.0), 1.0, evidence_ceiling), 2)
        return ConfidenceAssessment(
            score=score,
            factors=[
                f"alignment_score={alignment_score:.2f}",
                f"evidence_type={evidence_type}",
                f"evidence_ceiling={evidence_ceiling:.2f}",
                f"status={status}",
                "final_score=min(alignment_score,evidence_ceiling)",
            ],
        )
