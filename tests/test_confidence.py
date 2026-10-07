import pytest

from docsync_ai.scoring import ConfidenceScorer


def test_confidence_uses_lower_explainable_ceiling():
    result = ConfidenceScorer().assess(
        alignment_score=0.95,
        evidence_type="ambiguous_scope",
        status="NEEDS_SEMANTIC_REVIEW",
    )

    assert result.score == 0.75
    assert "final_score=min(alignment_score,evidence_ceiling)" in result.factors


def test_confidence_rejects_unknown_evidence_type():
    with pytest.raises(ValueError, match="Unknown evidence type"):
        ConfidenceScorer().assess(
            alignment_score=1.0,
            evidence_type="magic",
            status="CONFIRMED",
        )
