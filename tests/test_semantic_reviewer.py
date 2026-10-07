from docsync_ai.models import Finding, FindingSource, FindingStatus, SourceLocation
from docsync_ai.semantic import MockLLMProvider, SemanticReviewCache, SemanticReviewEngine


def _candidate(*, doc_name="path", doc_file="README.md", status=None):
    return Finding(
        rule_id="DS001",
        issue_type="PARAMETER_NAME_MISMATCH",
        severity="MEDIUM",
        confidence=0.85,
        code_location=SourceLocation("train.py", 1, 2),
        doc_location=SourceLocation(doc_file, 5, 5),
        code_fact={"entity": "train", "parameters": ["data_path", "epochs"]},
        doc_fact={"documented_parameter": doc_name, "text": f"{doc_name}: training data"},
        message="candidate",
        suggestion="review",
        status=status or FindingStatus.NEEDS_SEMANTIC_REVIEW,
        metadata={"alignment_score": 0.85, "alignment_evidence": ["train heading"]},
    )


def test_consistent_decision_resolves_candidate():
    outcome = SemanticReviewEngine(MockLLMProvider(["CONSISTENT"])).review([_candidate()])

    assert outcome.promoted_findings == []
    assert outcome.remaining_candidates == []
    assert outcome.reviews[0].final_status == FindingStatus.RESOLVED_CONSISTENT


def test_inconsistent_decision_promotes_ai_finding():
    outcome = SemanticReviewEngine(MockLLMProvider(["INCONSISTENT"])).review([_candidate()])

    assert len(outcome.promoted_findings) == 1
    promoted = outcome.promoted_findings[0]
    assert promoted.status == FindingStatus.CONFIRMED
    assert promoted.source == FindingSource.AI_SEMANTIC_REVIEW
    assert promoted.metadata["ai_decision"] == "INCONSISTENT"


def test_uncertain_decision_requires_manual_review():
    outcome = SemanticReviewEngine(MockLLMProvider(["UNCERTAIN"])).review([_candidate()])

    assert outcome.remaining_candidates[0].status == FindingStatus.NEEDS_MANUAL_REVIEW
    assert outcome.reviews[0].final_status == FindingStatus.NEEDS_MANUAL_REVIEW


def test_low_confidence_decision_requires_manual_review():
    response = {
        "decision": "INCONSISTENT",
        "confidence": 0.79,
        "reason": "Possible mismatch.",
        "matched_concept": "",
        "recommended_fix": "Review manually.",
    }
    outcome = SemanticReviewEngine(MockLLMProvider([response])).review([_candidate()])

    assert outcome.promoted_findings == []
    assert outcome.remaining_candidates[0].status == FindingStatus.NEEDS_MANUAL_REVIEW


def test_invalid_json_is_retried_then_succeeds():
    provider = MockLLMProvider(["invalid_json", "CONSISTENT"])
    outcome = SemanticReviewEngine(provider).review([_candidate()])

    assert provider.call_count == 2
    assert outcome.statistics.successful_reviews == 1
    assert outcome.reviews[0].attempts == 2


def test_timeout_exhaustion_degrades_safely():
    provider = MockLLMProvider(["timeout"])
    outcome = SemanticReviewEngine(provider).review([_candidate()])

    assert provider.call_count == 3
    assert outcome.statistics.failed_reviews == 1
    assert outcome.remaining_candidates[0].status == FindingStatus.NEEDS_MANUAL_REVIEW


def test_provider_exception_degrades_safely():
    provider = MockLLMProvider(["exception"])
    outcome = SemanticReviewEngine(provider, max_attempts=2).review([_candidate()])

    assert provider.call_count == 2
    assert outcome.reviews[0].error == "Mock provider exception"


def test_confirmed_finding_is_never_sent_to_provider():
    provider = MockLLMProvider(["INCONSISTENT"])
    outcome = SemanticReviewEngine(provider).review(
        [_candidate(status=FindingStatus.CONFIRMED)]
    )

    assert provider.call_count == 0
    assert outcome.promoted_findings == []


def test_external_provider_blocks_sensitive_candidate():
    provider = MockLLMProvider(["CONSISTENT"], external=True)
    outcome = SemanticReviewEngine(provider).review([_candidate(doc_file="secret/README.md")])

    assert provider.call_count == 0
    assert outcome.statistics.failed_reviews == 1
    assert "Sensitive source file" in outcome.reviews[0].error


def test_cache_hit_avoids_duplicate_provider_call(tmp_path):
    provider = MockLLMProvider(["CONSISTENT"])
    cache = SemanticReviewCache(tmp_path / "reviews.json")
    engine = SemanticReviewEngine(provider, cache=cache)

    first = engine.review([_candidate()])
    second = engine.review([_candidate()])

    assert first.statistics.cache_hits == 0
    assert second.statistics.cache_hits == 1
    assert provider.call_count == 1


def test_cache_invalidates_when_candidate_changes(tmp_path):
    provider = MockLLMProvider(["CONSISTENT", "INCONSISTENT"])
    cache = SemanticReviewCache(tmp_path / "reviews.json")
    engine = SemanticReviewEngine(provider, cache=cache)

    engine.review([_candidate(doc_name="path")])
    outcome = engine.review([_candidate(doc_name="dataset_file")])

    assert provider.call_count == 2
    assert outcome.statistics.cache_hits == 0


def test_cache_contains_no_provider_credentials(tmp_path):
    provider = MockLLMProvider(["CONSISTENT"], model="model-without-secret")
    cache_path = tmp_path / "reviews.json"
    SemanticReviewEngine(provider, cache=SemanticReviewCache(cache_path)).review([_candidate()])

    cache_text = cache_path.read_text(encoding="utf-8")
    assert "API_KEY" not in cache_text
    assert "token" not in cache_text.casefold()
