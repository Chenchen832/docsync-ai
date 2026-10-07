"""Static JSON, TOML, and conservative YAML configuration parsing."""

from __future__ import annotations

import ast
import json
import re
import tomllib
from pathlib import Path
from typing import Any

from docsync_ai.models import CodeEntity

_YAML_KEY_RE = re.compile(r"^(?P<indent>\s*)(?P<key>[A-Za-z0-9_.-]+)\s*:\s*(?P<value>.*)$")


def _safe_yaml_scalar(value: str) -> Any:
    stripped = value.strip()
    lowered = stripped.casefold()
    if lowered in {"null", "none", "~"}:
        return None
    if lowered in {"true", "yes"}:
        return True
    if lowered in {"false", "no"}:
        return False
    try:
        return ast.literal_eval(stripped)
    except (ValueError, SyntaxError):
        return stripped.strip("\"'")


class ConfigParser:
    """Extract nested keys without evaluating code or custom YAML tags."""

    SUPPORTED_SUFFIXES = {".json": "json", ".yaml": "yaml", ".yml": "yaml", ".toml": "toml"}

    def parse_file(self, file_path: str | Path) -> list[CodeEntity]:
        path = Path(file_path)
        format_name = self.SUPPORTED_SUFFIXES.get(path.suffix.casefold())
        if format_name is None:
            raise ValueError(f"Unsupported config format: {path.suffix}")
        return self.parse(
            path.read_text(encoding="utf-8"),
            format_name=format_name,
            file_path=str(path),
        )

    def parse(
        self,
        text: str,
        *,
        format_name: str,
        file_path: str = "<memory>",
        line_offset: int = 0,
    ) -> list[CodeEntity]:
        normalized_format = format_name.casefold().removeprefix(".")
        if normalized_format in {"yaml", "yml"}:
            return self._parse_yaml(text, file_path=file_path, line_offset=line_offset)
        if normalized_format == "json":
            data = json.loads(text)
        elif normalized_format == "toml":
            data = tomllib.loads(text)
        else:
            raise ValueError(f"Unsupported config format: {format_name}")
        if not isinstance(data, dict):
            return []
        entities: list[CodeEntity] = []
        self._flatten_mapping(
            data,
            text=text,
            file_path=file_path,
            format_name=normalized_format,
            line_offset=line_offset,
            entities=entities,
        )
        return entities

    def _flatten_mapping(
        self,
        mapping: dict[str, Any],
        *,
        text: str,
        file_path: str,
        format_name: str,
        line_offset: int,
        entities: list[CodeEntity],
        prefix: str = "",
    ) -> None:
        for key, value in mapping.items():
            key_text = str(key)
            nested_path = f"{prefix}.{key_text}" if prefix else key_text
            line = self._find_key_line(text, key_text, format_name) + line_offset
            entities.append(
                self._entity(
                    name=key_text,
                    nested_path=nested_path,
                    value=value,
                    file_path=file_path,
                    line=line,
                    format_name=format_name,
                    line_precision="best_effort",
                )
            )
            if isinstance(value, dict):
                self._flatten_mapping(
                    value,
                    text=text,
                    file_path=file_path,
                    format_name=format_name,
                    line_offset=line_offset,
                    entities=entities,
                    prefix=nested_path,
                )

    def _parse_yaml(self, text: str, *, file_path: str, line_offset: int) -> list[CodeEntity]:
        stack: list[tuple[int, str]] = []
        entities: list[CodeEntity] = []
        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            stripped = raw_line.strip()
            if not stripped or stripped.startswith(("#", "---", "...", "- ")):
                continue
            match = _YAML_KEY_RE.match(raw_line)
            if not match:
                continue
            indent = len(match.group("indent").expandtabs(2))
            while stack and indent <= stack[-1][0]:
                stack.pop()
            key = match.group("key")
            raw_value = match.group("value").split(" #", 1)[0].strip()
            nested_path = ".".join([*(item[1] for item in stack), key])
            value = {} if not raw_value else _safe_yaml_scalar(raw_value)
            entities.append(
                self._entity(
                    name=key,
                    nested_path=nested_path,
                    value=value,
                    file_path=file_path,
                    line=line_number + line_offset,
                    format_name="yaml",
                    line_precision="exact",
                )
            )
            if not raw_value:
                stack.append((indent, key))
        return entities

    @staticmethod
    def _find_key_line(text: str, key: str, format_name: str) -> int:
        escaped = re.escape(key)
        if format_name == "json":
            pattern = re.compile(rf'^\s*"{escaped}"\s*:', re.MULTILINE)
        else:
            pattern = re.compile(
                rf"^\s*{escaped}\s*=|^\s*\[[^\]]*\b{escaped}\b[^\]]*\]", re.MULTILINE
            )
        match = pattern.search(text)
        return text[: match.start()].count("\n") + 1 if match else 1

    @staticmethod
    def _entity(
        *,
        name: str,
        nested_path: str,
        value: Any,
        file_path: str,
        line: int,
        format_name: str,
        line_precision: str,
    ) -> CodeEntity:
        return CodeEntity(
            entity_type="config_key",
            name=name,
            qualified_name=nested_path,
            file_path=file_path,
            line_start=line,
            line_end=line,
            default_values={nested_path: value},
            metadata={
                "nested_path": nested_path,
                "value": value,
                "format": format_name,
                "line_precision": line_precision,
            },
        )


def parse_config_file(file_path: str | Path) -> list[CodeEntity]:
    return ConfigParser().parse_file(file_path)
