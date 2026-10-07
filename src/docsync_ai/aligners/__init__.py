"""Deterministic code-documentation entity alignment."""

from .entity_aligner import EntityAligner
from .normalizer import normalize_identifier, normalize_qualified_name

__all__ = ["EntityAligner", "normalize_identifier", "normalize_qualified_name"]
