"""Calibrated semantic decision policy.

This policy was selected on the independent ``semantic-calibration-v1`` set.
It must not be tuned against the frozen benchmark-v1 semantic cases.
"""

from __future__ import annotations

from docsync_ai.semantic.schemas import SemanticDecision

SEMANTIC_POLICY_VERSION = "semantic-policy-v2"
CONSISTENT_CONFIDENCE_OFFSET = 0.10


def apply_semantic_policy(
    decision: SemanticDecision,
    confidence: float,
    *,
    inconsistent_threshold: float = 0.80,
) -> SemanticDecision:
    """Return the accepted decision or ``UNCERTAIN`` for manual review.

    Calibration showed that correct synonym/equivalence decisions commonly
    receive confidence between 0.70 and 0.79, while confirmed inconsistency
    decisions were supported only at 0.95 or above.  The policy therefore
    retains the configured threshold for inconsistency promotion and uses a
    0.10 lower acceptance floor for consistent resolutions.
    """

    if not 0.0 <= inconsistent_threshold <= 1.0:
        raise ValueError("inconsistent_threshold must be between 0.0 and 1.0")
    if decision == SemanticDecision.UNCERTAIN:
        return SemanticDecision.UNCERTAIN
    threshold = inconsistent_threshold
    if decision == SemanticDecision.CONSISTENT:
        threshold = max(
            0.0,
            round(inconsistent_threshold - CONSISTENT_CONFIDENCE_OFFSET, 10),
        )
    return decision if confidence >= threshold else SemanticDecision.UNCERTAIN
