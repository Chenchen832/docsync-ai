"""Conservative identifier normalization used by deterministic aligners."""

from __future__ import annotations

import re


def normalize_identifier(value: str) -> str:
    """Normalize case and the CLI hyphen/Python underscore convention."""

    normalized = value.strip().casefold()
    normalized = normalized.removeprefix("--")
    normalized = normalized.replace("-", "_")
    return re.sub(r"_+", "_", normalized)


def normalize_qualified_name(value: str) -> str:
    return ".".join(normalize_identifier(part) for part in value.strip().split("."))
