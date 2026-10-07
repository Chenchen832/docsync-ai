import json

import pytest

from docsync_ai.semantic import SchemaValidationError, SemanticDecision, SemanticReviewResult


def _valid_payload(**changes):
    payload = {
        "decision": "CONSISTENT",
        "confidence": 0.91,
        "reason": "Both names describe the dataset path.",
        "matched_concept": "dataset path",
        "recommended_fix": "",
        "evidence_summary": "The surrounding parameter descriptions agree.",
    }
    payload.update(changes)
    return payload


@pytest.mark.parametrize("decision", ["CONSISTENT", "INCONSISTENT", "UNCERTAIN"])
def test_semantic_schema_accepts_supported_decisions(decision):
    result = SemanticReviewResult.from_mapping(_valid_payload(decision=decision))

    assert result.decision == SemanticDecision(decision)
    assert result.to_dict()["decision"] == decision


def test_semantic_schema_accepts_json_text():
    result = SemanticReviewResult.from_json(json.dumps(_valid_payload()))

    assert result.confidence == 0.91


@pytest.mark.parametrize(
    "payload",
    [
        _valid_payload(decision="MAYBE"),
        _valid_payload(confidence=1.1),
        _valid_payload(confidence=True),
        _valid_payload(reason=""),
        {key: value for key, value in _valid_payload().items() if key != "reason"},
        _valid_payload(extra="not allowed"),
    ],
)
def test_semantic_schema_rejects_invalid_payloads(payload):
    with pytest.raises(SchemaValidationError):
        SemanticReviewResult.from_mapping(payload)


def test_semantic_schema_rejects_invalid_json():
    with pytest.raises(SchemaValidationError, match="invalid JSON"):
        SemanticReviewResult.from_json("{not-json")
