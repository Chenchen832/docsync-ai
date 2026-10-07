"""Provider abstraction, deterministic mock, and OpenAI-compatible HTTP client."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import Any

from docsync_ai.semantic.schemas import ProviderResponse, SemanticDecision


class ProviderError(RuntimeError):
    pass


class ProviderConfigurationError(ProviderError):
    pass


class ProviderTimeoutError(ProviderError):
    pass


class BaseLLMProvider(ABC):
    provider_name = "base"
    is_external = True

    def __init__(self, *, model: str) -> None:
        self.model = model

    @abstractmethod
    def complete(self, *, system_prompt: str, user_prompt: str) -> ProviderResponse:
        """Return raw model content. Validation belongs to the reviewer."""


class MockLLMProvider(BaseLLMProvider):
    provider_name = "mock"
    is_external = False

    def __init__(
        self,
        outcomes: Iterable[str | dict[str, Any] | Exception] | None = None,
        *,
        model: str = "mock-semantic-v1",
        external: bool = False,
    ) -> None:
        super().__init__(model=model)
        self.outcomes = list(outcomes or [SemanticDecision.UNCERTAIN.value])
        self.is_external = external
        self.call_count = 0

    def complete(self, *, system_prompt: str, user_prompt: str) -> ProviderResponse:
        del system_prompt, user_prompt
        self.call_count += 1
        outcome = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(outcome, Exception):
            if isinstance(outcome, TimeoutError):
                raise ProviderTimeoutError("Mock timeout") from outcome
            raise ProviderError("Mock provider exception") from outcome
        if outcome == "timeout":
            raise ProviderTimeoutError("Mock timeout")
        if outcome == "exception":
            raise ProviderError("Mock provider exception")
        if outcome == "invalid_json":
            content = "{invalid json"
        elif isinstance(outcome, dict):
            content = json.dumps(outcome, ensure_ascii=False)
        else:
            content = json.dumps(self._decision_payload(str(outcome)), ensure_ascii=False)
        return ProviderResponse(content=content, latency_ms=1.0, input_tokens=20, output_tokens=12)

    @staticmethod
    def _decision_payload(decision: str) -> dict[str, Any]:
        normalized = SemanticDecision(decision).value
        confidence = 0.95 if normalized != SemanticDecision.UNCERTAIN.value else 0.50
        return {
            "decision": normalized,
            "confidence": confidence,
            "reason": f"Mock decision: {normalized}",
            "matched_concept": "dataset path" if normalized == "CONSISTENT" else "",
            "recommended_fix": (
                "Use the current code parameter name."
                if normalized == "INCONSISTENT"
                else ""
            ),
            "evidence_summary": "Deterministic offline mock response.",
        }


class OpenAICompatibleProvider(BaseLLMProvider):
    provider_name = "openai-compatible"
    is_external = True

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout: float = 30.0,
    ) -> None:
        if not api_key or not base_url or not model:
            raise ProviderConfigurationError(
                "DOCSYNC_AI_API_KEY, DOCSYNC_AI_BASE_URL and DOCSYNC_AI_MODEL are required"
            )
        super().__init__(model=model)
        self._api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> OpenAICompatibleProvider:
        values = os.environ if environ is None else environ
        raw_timeout = values.get("DOCSYNC_AI_TIMEOUT", "30")
        try:
            timeout = float(raw_timeout)
        except ValueError as exc:
            raise ProviderConfigurationError("DOCSYNC_AI_TIMEOUT must be numeric") from exc
        return cls(
            api_key=values.get("DOCSYNC_AI_API_KEY", ""),
            base_url=values.get("DOCSYNC_AI_BASE_URL", ""),
            model=values.get("DOCSYNC_AI_MODEL", ""),
            timeout=timeout,
        )

    def complete(self, *, system_prompt: str, user_prompt: str) -> ProviderResponse:
        body = json.dumps(
            {
                "model": self.model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except TimeoutError as exc:
            raise ProviderTimeoutError("OpenAI-compatible request timed out") from exc
        except urllib.error.HTTPError as exc:
            raise ProviderError(f"OpenAI-compatible HTTP error: {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise ProviderError("OpenAI-compatible network error") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ProviderError(
                "OpenAI-compatible endpoint returned invalid response JSON"
            ) from exc
        latency_ms = (time.perf_counter() - started) * 1000
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("OpenAI-compatible response is missing message content") from exc
        if not isinstance(content, str):
            raise ProviderError("OpenAI-compatible message content must be text")
        usage = payload.get("usage") or {}
        return ProviderResponse(
            content=content,
            latency_ms=latency_ms,
            input_tokens=_optional_int(usage.get("prompt_tokens")),
            output_tokens=_optional_int(usage.get("completion_tokens")),
        )


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
