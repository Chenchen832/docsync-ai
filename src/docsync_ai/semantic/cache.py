"""Credential-free JSON cache for validated semantic review results."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from docsync_ai.semantic.prompts import PROMPT_VERSION
from docsync_ai.semantic.schemas import SemanticReviewRequest, SemanticReviewResult


class SemanticReviewCache:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def make_key(self, request: SemanticReviewRequest, *, model: str) -> str:
        content = {
            "model": model,
            "candidate": request.payload,
            "code_context": request.payload.get("code_context", ""),
            "doc_context": request.payload.get("doc_context", ""),
            "prompt_version": PROMPT_VERSION,
        }
        encoded = json.dumps(content, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def get(self, key: str) -> SemanticReviewResult | None:
        data = self._read()
        cached = data.get(key)
        if not isinstance(cached, dict):
            return None
        try:
            return SemanticReviewResult.from_mapping(cached.get("result"))
        except ValueError:
            return None

    def set(self, key: str, result: SemanticReviewResult, *, model: str) -> None:
        data = self._read()
        data[key] = {
            "model": model,
            "prompt_version": PROMPT_VERSION,
            "result": result.to_dict(),
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary.write_text(
                json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            temporary.replace(self.path)
        except OSError:
            # Cache availability must never decide whether the scan succeeds.
            return

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}
