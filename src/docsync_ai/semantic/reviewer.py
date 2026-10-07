"""Semantic candidate review orchestration, retry, cache, and safe degradation."""

from __future__ import annotations

from dataclasses import replace

from docsync_ai.models import Finding, FindingSource, FindingStatus
from docsync_ai.semantic.cache import SemanticReviewCache
from docsync_ai.semantic.config import MAX_SEMANTIC_REVIEW_ATTEMPTS, SEMANTIC_REVIEW_THRESHOLD
from docsync_ai.semantic.policy import SEMANTIC_POLICY_VERSION, apply_semantic_policy
from docsync_ai.semantic.prompts import build_review_request
from docsync_ai.semantic.provider import BaseLLMProvider, ProviderError
from docsync_ai.semantic.schemas import (
    AIStatistics,
    ProviderResponse,
    SchemaValidationError,
    SemanticDecision,
    SemanticReviewOutcome,
    SemanticReviewRecord,
    SemanticReviewRequest,
    SemanticReviewResult,
)
from docsync_ai.semantic.security import candidate_involves_sensitive_file


class SemanticReviewEngine:
    def __init__(
        self,
        provider: BaseLLMProvider,
        *,
        cache: SemanticReviewCache | None = None,
        threshold: float = SEMANTIC_REVIEW_THRESHOLD,
        max_attempts: int = MAX_SEMANTIC_REVIEW_ATTEMPTS,
    ) -> None:
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("Semantic review threshold must be between 0.0 and 1.0")
        if max_attempts < 1 or max_attempts > 5:
            raise ValueError("max_attempts must be between 1 and 5")
        self.provider = provider
        self.cache = cache
        self.threshold = threshold
        self.max_attempts = max_attempts

    def review(self, candidates: list[Finding]) -> SemanticReviewOutcome:
        eligible = [
            item
            for item in candidates
            if item.status == FindingStatus.NEEDS_SEMANTIC_REVIEW and item.rule_id == "DS001"
        ]
        untouched = [item for item in candidates if item not in eligible]
        promoted: list[Finding] = []
        remaining: list[Finding] = list(untouched)
        records: list[SemanticReviewRecord] = []
        latencies: list[float] = []
        input_tokens: list[int] = []
        output_tokens: list[int] = []
        cache_hits = 0
        failures = 0
        successes = 0

        for candidate in eligible:
            request = build_review_request(candidate)
            if self.provider.is_external and candidate_involves_sensitive_file(candidate):
                failures += 1
                remaining.append(
                    self._manual_candidate(candidate, candidate_id=request.candidate_id)
                )
                records.append(
                    self._failure_record(
                        candidate,
                        candidate_id=request.candidate_id,
                        error="Sensitive source file blocked from external semantic review",
                    )
                )
                continue

            result: SemanticReviewResult | None = None
            response: ProviderResponse | None = None
            attempts = 0
            error: str | None = None
            cache_hit = False
            cache_key = (
                self.cache.make_key(request, model=self.provider.model) if self.cache else None
            )
            if self.cache and cache_key:
                result = self.cache.get(cache_key)
                cache_hit = result is not None
                cache_hits += int(cache_hit)

            if result is None:
                result, response, attempts, error = self._request_with_retry(request)
                if result is not None and self.cache and cache_key:
                    self.cache.set(cache_key, result, model=self.provider.model)

            if result is None:
                failures += 1
                remaining.append(
                    self._manual_candidate(candidate, candidate_id=request.candidate_id)
                )
                record = self._failure_record(
                    candidate,
                    candidate_id=request.candidate_id,
                    error=error or "Semantic review failed",
                )
                record.attempts = attempts
                records.append(record)
                continue

            successes += 1
            if response is not None:
                latencies.append(response.latency_ms)
                if response.input_tokens is not None:
                    input_tokens.append(response.input_tokens)
                if response.output_tokens is not None:
                    output_tokens.append(response.output_tokens)
            final_status = self._final_status(result)
            if final_status == FindingStatus.CONFIRMED:
                promoted.append(self._promote(candidate, result, request.candidate_id))
            elif final_status == FindingStatus.NEEDS_MANUAL_REVIEW:
                remaining.append(
                    self._manual_candidate(candidate, candidate_id=request.candidate_id)
                )

            records.append(
                SemanticReviewRecord(
                    candidate_id=request.candidate_id,
                    provider=self.provider.provider_name,
                    model=self.provider.model,
                    decision=result.decision.value,
                    confidence=result.confidence,
                    reason=result.reason,
                    matched_concept=result.matched_concept,
                    recommended_fix=result.recommended_fix,
                    evidence_summary=result.evidence_summary,
                    final_status=final_status,
                    latency_ms=response.latency_ms if response else 0.0,
                    cache_hit=cache_hit,
                    attempts=attempts,
                    candidate_snapshot=request.payload,
                    policy_version=SEMANTIC_POLICY_VERSION,
                )
            )

        statistics = AIStatistics(
            enabled=True,
            provider=self.provider.provider_name,
            model=self.provider.model,
            candidate_count=len(eligible),
            reviewed_count=len(eligible),
            successful_reviews=successes,
            failed_reviews=failures,
            cache_hits=cache_hits,
            average_latency_ms=round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
            input_tokens=sum(input_tokens) if input_tokens else None,
            output_tokens=sum(output_tokens) if output_tokens else None,
            policy_version=SEMANTIC_POLICY_VERSION,
        )
        return SemanticReviewOutcome(promoted, remaining, records, statistics)

    def _request_with_retry(
        self, request: SemanticReviewRequest
    ) -> tuple[SemanticReviewResult | None, ProviderResponse | None, int, str | None]:
        last_error: str | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.provider.complete(
                    system_prompt=request.system_prompt,
                    user_prompt=request.user_prompt,
                )
                result = SemanticReviewResult.from_json(response.content)
                return result, response, attempt, None
            except (ProviderError, SchemaValidationError) as exc:
                last_error = str(exc)
        return None, None, self.max_attempts, last_error

    def _final_status(self, result: SemanticReviewResult) -> str:
        accepted = apply_semantic_policy(
            result.decision,
            result.confidence,
            inconsistent_threshold=self.threshold,
        )
        if accepted == SemanticDecision.UNCERTAIN:
            return FindingStatus.NEEDS_MANUAL_REVIEW
        if accepted == SemanticDecision.CONSISTENT:
            return FindingStatus.RESOLVED_CONSISTENT
        return FindingStatus.CONFIRMED

    def _promote(
        self, candidate: Finding, result: SemanticReviewResult, candidate_id: str
    ) -> Finding:
        return replace(
            candidate,
            status=FindingStatus.CONFIRMED,
            source=FindingSource.AI_SEMANTIC_REVIEW,
            confidence=result.confidence,
            message=result.reason,
            suggestion=result.recommended_fix or candidate.suggestion,
            metadata={
                **candidate.metadata,
                "candidate_id": candidate_id,
                "ai_provider": self.provider.provider_name,
                "ai_model": self.provider.model,
                "ai_decision": result.decision.value,
                "ai_confidence": result.confidence,
                "ai_reason": result.reason,
                "semantic_policy_version": SEMANTIC_POLICY_VERSION,
                "original_candidate_confidence": candidate.confidence,
            },
        )

    def _failure_record(
        self, candidate: Finding, *, candidate_id: str, error: str
    ) -> SemanticReviewRecord:
        return SemanticReviewRecord(
            candidate_id=candidate_id,
            provider=self.provider.provider_name,
            model=self.provider.model,
            decision=SemanticDecision.UNCERTAIN.value,
            confidence=None,
            reason="Semantic review unavailable; manual review required.",
            final_status=FindingStatus.NEEDS_MANUAL_REVIEW,
            error=error,
            candidate_snapshot=build_review_request(candidate).payload,
            policy_version=SEMANTIC_POLICY_VERSION,
        )

    @staticmethod
    def _manual_candidate(candidate: Finding, *, candidate_id: str) -> Finding:
        return replace(
            candidate,
            status=FindingStatus.NEEDS_MANUAL_REVIEW,
            metadata={**candidate.metadata, "candidate_id": candidate_id},
        )


def unavailable_review_outcome(candidates: list[Finding], *, reason: str) -> SemanticReviewOutcome:
    eligible = [
        item
        for item in candidates
        if item.status == FindingStatus.NEEDS_SEMANTIC_REVIEW and item.rule_id == "DS001"
    ]
    eligible_ids = {id(item): build_review_request(item) for item in eligible}
    remaining = []
    for item in candidates:
        request = eligible_ids.get(id(item))
        if request is None:
            remaining.append(item)
        else:
            remaining.append(
                replace(
                    item,
                    status=FindingStatus.NEEDS_MANUAL_REVIEW,
                    metadata={**item.metadata, "candidate_id": request.candidate_id},
                )
            )
    records = []
    for item in eligible:
        request = eligible_ids[id(item)]
        records.append(
            SemanticReviewRecord(
                candidate_id=request.candidate_id,
                provider="unavailable",
                model="",
                decision=SemanticDecision.UNCERTAIN.value,
                confidence=None,
                reason="Semantic review unavailable; manual review required.",
                final_status=FindingStatus.NEEDS_MANUAL_REVIEW,
                error=reason,
                candidate_snapshot=request.payload,
                policy_version=SEMANTIC_POLICY_VERSION,
            )
        )
    return SemanticReviewOutcome(
        promoted_findings=[],
        remaining_candidates=remaining,
        reviews=records,
        statistics=AIStatistics(
            enabled=True,
            provider="unavailable",
            model=None,
            candidate_count=len(eligible),
            reviewed_count=0,
            successful_reviews=0,
            failed_reviews=len(eligible),
            policy_version=SEMANTIC_POLICY_VERSION,
        ),
    )
