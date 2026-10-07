import pytest

from docsync_ai.semantic import (
    SEMANTIC_POLICY_VERSION,
    SemanticDecision,
    apply_semantic_policy,
)


def test_policy_version_is_frozen_v2():
    assert SEMANTIC_POLICY_VERSION == "semantic-policy-v2"


@pytest.mark.parametrize("confidence", [0.70, 0.75, 1.0])
def test_consistent_decision_uses_calibrated_lower_floor(confidence):
    assert (
        apply_semantic_policy(SemanticDecision.CONSISTENT, confidence)
        == SemanticDecision.CONSISTENT
    )


def test_consistent_below_calibrated_floor_requires_review():
    assert (
        apply_semantic_policy(SemanticDecision.CONSISTENT, 0.69)
        == SemanticDecision.UNCERTAIN
    )


def test_inconsistent_decision_retains_point_eight_threshold():
    assert (
        apply_semantic_policy(SemanticDecision.INCONSISTENT, 0.80)
        == SemanticDecision.INCONSISTENT
    )
    assert (
        apply_semantic_policy(SemanticDecision.INCONSISTENT, 0.79)
        == SemanticDecision.UNCERTAIN
    )


def test_explicit_uncertain_is_never_overridden_by_confidence():
    assert (
        apply_semantic_policy(SemanticDecision.UNCERTAIN, 0.99)
        == SemanticDecision.UNCERTAIN
    )


def test_policy_rejects_invalid_threshold():
    with pytest.raises(ValueError, match="between 0.0 and 1.0"):
        apply_semantic_policy(
            SemanticDecision.CONSISTENT,
            0.90,
            inconsistent_threshold=1.01,
        )
