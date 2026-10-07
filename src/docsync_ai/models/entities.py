"""Serializable data structures shared by parsers, rules, and reporters."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


class FindingStatus:
    CONFIRMED = "CONFIRMED"
    NEEDS_SEMANTIC_REVIEW = "NEEDS_SEMANTIC_REVIEW"
    NEEDS_MANUAL_REVIEW = "NEEDS_MANUAL_REVIEW"
    RESOLVED_CONSISTENT = "RESOLVED_CONSISTENT"


class FindingSource:
    DETERMINISTIC_RULE = "DETERMINISTIC_RULE"
    AI_SEMANTIC_REVIEW = "AI_SEMANTIC_REVIEW"


def _json_safe(value: Any) -> Any:
    """Convert common Python values to structures accepted by ``json``."""

    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


@dataclass(slots=True)
class SourceLocation:
    """A precise location in a source or documentation file."""

    file_path: str
    line_start: int
    line_end: int

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(asdict(self))


@dataclass(slots=True)
class CodeEntity:
    """A normalized fact extracted from Python source code."""

    entity_type: str
    name: str
    qualified_name: str
    file_path: str
    line_start: int
    line_end: int
    parameters: list[str] = field(default_factory=list)
    default_values: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def location(self) -> SourceLocation:
        return SourceLocation(self.file_path, self.line_start, self.line_end)

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(asdict(self))


@dataclass(slots=True)
class DocEntity:
    """A normalized fact extracted from Markdown documentation."""

    entity_type: str
    name: str
    text: str
    file_path: str
    line_start: int
    line_end: int
    code_snippet: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def location(self) -> SourceLocation:
        return SourceLocation(self.file_path, self.line_start, self.line_end)

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(asdict(self))


@dataclass(slots=True)
class Finding:
    """A rule finding designed for later AI review and Web presentation."""

    rule_id: str
    issue_type: str
    severity: str
    confidence: float
    code_location: SourceLocation
    doc_location: SourceLocation
    code_fact: Any
    doc_fact: Any
    message: str
    suggestion: str
    status: str = FindingStatus.CONFIRMED
    source: str = FindingSource.DETERMINISTIC_RULE
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(asdict(self))


@dataclass(slots=True)
class AlignmentCandidate:
    """An explainable relationship between a code fact and a documentation fact."""

    code_entity: CodeEntity
    doc_entity: DocEntity
    alignment_type: str
    alignment_score: float
    evidence: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(asdict(self))
