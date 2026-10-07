"""Sensitive-path detection and minimal redaction before external review."""

from __future__ import annotations

import re
from pathlib import Path

from docsync_ai.models import Finding

_SENSITIVE_NAMES = {".env", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519"}
_SENSITIVE_PARTS = {"credential", "credentials", "secret", "secrets", "token", "tokens"}
_SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?i)\b((?:[a-z0-9]+[_-])*(?:api[_-]?key|token|password|passwd|secret|credential)s?)"
    r"\b\s*[:=]\s*([^\s,;]+)"
)


def is_sensitive_path(file_path: str) -> bool:
    path = Path(file_path)
    name = path.name.casefold()
    if (
        name in _SENSITIVE_NAMES
        or name.startswith(".env.")
        or path.suffix.casefold() in {".pem", ".key", ".p12", ".pfx"}
    ):
        return True
    return any(
        part.casefold() in _SENSITIVE_PARTS
        or Path(part).stem.casefold() in _SENSITIVE_PARTS
        for part in path.parts
    )


def redact_sensitive_text(text: str, *, limit: int = 1200) -> str:
    bounded = text[:limit]
    return _SENSITIVE_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", bounded)


def candidate_involves_sensitive_file(candidate: Finding) -> bool:
    return is_sensitive_path(candidate.code_location.file_path) or is_sensitive_path(
        candidate.doc_location.file_path
    )
