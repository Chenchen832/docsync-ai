"""Line-aware Markdown extraction for Phase 1.

The implementation intentionally uses a small deterministic scanner instead of
rendering Markdown. It preserves locations and uses Python AST only to inspect
code examples; examples are never executed.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from docsync_ai.models import DocEntity
from docsync_ai.parsers.config_parser import ConfigParser

_FENCE_RE = re.compile(r"^\s*(```+|~~~+)\s*([^\s`]*)?.*$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_DEFAULT_RE = re.compile(
    r"(?P<name>--[A-Za-z0-9][\w-]*|[A-Za-z_]\w*)\s*"
    r"(?:的\s*)?"
    r"(?:默认值?(?:为|是)?|default(?:\s+value)?\s*(?:is|=|:))\s*"
    r"(?P<value>\[[^\]\n]*\]|\{[^}\n]*\}|\([^\)\n]*\)|\"[^\"\n]*\"|'[^'\n]*'|[^\s,，。;；)）]+)",
    re.IGNORECASE,
)
_DEFAULT_CELL_RE = re.compile(
    r"(?:默认值?|default(?:\s+value)?)\s*(?:为|是|is|=|:|：)\s*(?P<value>.+?)\s*$",
    re.IGNORECASE,
)
_PARAMETER_SECTION_RE = re.compile(r"^(?:parameters?|参数(?:说明)?)\s*[:：]?\s*$", re.IGNORECASE)
_PARAMETER_ITEM_RE = re.compile(
    r"^\s*[-*+]\s+`?(?P<name>[A-Za-z_]\w*)`?\s*[:：]\s*(?P<description>.+)$"
)
_CLI_FLAG_RE = re.compile(r"(?<!\w)(--[A-Za-z0-9][\w-]*)(?:[=\s]+([^\s]+))?")


def _safe_expression(node: ast.AST) -> Any:
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return ast.unparse(node)
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, (set, frozenset)):
        return sorted(value, key=repr)
    return value


def _safe_text_value(text: str) -> Any:
    value = text.strip().strip("`*_").rstrip(":,，。;；")
    try:
        return _safe_expression(ast.parse(value, mode="eval").body)
    except SyntaxError:
        return value


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ast.unparse(node)


class MarkdownParser:
    """Extract headings, prose, inline code, code blocks, calls, and CLI commands."""

    def parse_file(self, file_path: str | Path) -> list[DocEntity]:
        path = Path(file_path)
        text = path.read_text(encoding="utf-8")
        return self.parse(text, file_path=str(path))

    def parse(self, text: str, *, file_path: str = "<memory>") -> list[DocEntity]:
        lines = text.splitlines()
        entities: list[DocEntity] = []
        paragraph: list[tuple[int, str]] = []
        heading = ""
        in_fence = False
        fence_marker = ""
        fence_language = ""
        fence_start = 0
        fence_lines: list[str] = []

        def flush_paragraph() -> None:
            nonlocal paragraph
            if paragraph:
                entities.extend(self._paragraph_entities(paragraph, file_path, heading))
                paragraph = []

        for line_number, line in enumerate(lines, start=1):
            if in_fence:
                stripped = line.lstrip()
                if stripped.startswith(fence_marker):
                    entities.extend(
                        self._code_entities(
                            fence_lines,
                            file_path=file_path,
                            language=fence_language,
                            fence_start=fence_start,
                            fence_end=line_number,
                            heading=heading,
                        )
                    )
                    in_fence = False
                    fence_lines = []
                    continue
                fence_lines.append(line)
                continue

            fence_match = _FENCE_RE.match(line)
            if fence_match:
                flush_paragraph()
                in_fence = True
                fence_marker = fence_match.group(1)
                fence_language = (fence_match.group(2) or "").lower()
                fence_start = line_number
                fence_lines = []
                continue

            heading_match = _HEADING_RE.match(line)
            if heading_match:
                flush_paragraph()
                heading = heading_match.group(2).strip()
                entities.append(
                    DocEntity(
                        entity_type="heading",
                        name=heading,
                        text=heading,
                        file_path=file_path,
                        line_start=line_number,
                        line_end=line_number,
                        metadata={"level": len(heading_match.group(1))},
                    )
                )
                entities.extend(
                    self._inline_code_entities(
                        line,
                        file_path=file_path,
                        line_number=line_number,
                        heading=heading,
                    )
                )
                continue

            if not line.strip():
                flush_paragraph()
            else:
                paragraph.append((line_number, line))

        flush_paragraph()
        if in_fence:
            entities.extend(
                self._code_entities(
                    fence_lines,
                    file_path=file_path,
                    language=fence_language,
                    fence_start=fence_start,
                    fence_end=max(fence_start, len(lines)),
                    heading=heading,
                    closed=False,
                )
            )
        return entities

    def _paragraph_entities(
        self, lines: list[tuple[int, str]], file_path: str, heading: str
    ) -> list[DocEntity]:
        start, end = lines[0][0], lines[-1][0]
        text = "\n".join(item[1].strip() for item in lines)
        entities = [
            DocEntity(
                entity_type="paragraph",
                name=heading or f"paragraph@{start}",
                text=text,
                file_path=file_path,
                line_start=start,
                line_end=end,
                metadata={"context_heading": heading},
            )
        ]
        for line_number, line in lines:
            entities.extend(
                self._inline_code_entities(
                    line,
                    file_path=file_path,
                    line_number=line_number,
                    heading=heading,
                )
            )

        cleaned = text.replace("`", "")
        for match in _DEFAULT_RE.finditer(cleaned):
            line_offset = cleaned[: match.start()].count("\n")
            parameter_name = match.group("name")
            default_value = _safe_text_value(match.group("value"))
            entities.append(
                DocEntity(
                    entity_type="declared_default",
                    name=parameter_name,
                    text=match.group(0),
                    file_path=file_path,
                    line_start=start + line_offset,
                    line_end=start + line_offset,
                    code_snippet=match.group(0),
                    metadata={
                        "parameter_name": parameter_name,
                        "default_value": default_value,
                        "raw_value": match.group("value"),
                        "context_heading": heading,
                        "declaration_kind": "prose",
                    },
                )
            )

        parameter_section = bool(re.search(r"parameters?|参数", heading, re.IGNORECASE))
        for line_number, line in lines:
            cleaned_line = line.replace("`", "").strip()
            if _PARAMETER_SECTION_RE.fullmatch(cleaned_line):
                parameter_section = True
                continue

            parameter_match = _PARAMETER_ITEM_RE.match(line)
            if parameter_section and parameter_match:
                entities.append(
                    DocEntity(
                        entity_type="documented_parameter",
                        name=parameter_match.group("name"),
                        text=line.strip(),
                        file_path=file_path,
                        line_start=line_number,
                        line_end=line_number,
                        metadata={
                            "description": parameter_match.group("description").strip(),
                            "context_heading": heading,
                            "declaration_kind": "parameter_list",
                        },
                    )
                )

            if "|" not in cleaned_line:
                continue
            cells = [cell.strip() for cell in cleaned_line.strip("|").split("|")]
            if len(cells) < 2 or not re.fullmatch(r"[A-Za-z_]\w*|--[\w-]+", cells[0]):
                continue
            for cell in cells[1:]:
                default_match = _DEFAULT_CELL_RE.search(cell)
                if not default_match:
                    continue
                entities.append(
                    DocEntity(
                        entity_type="declared_default",
                        name=cells[0],
                        text=line.strip(),
                        file_path=file_path,
                        line_start=line_number,
                        line_end=line_number,
                        code_snippet=line.strip(),
                        metadata={
                            "parameter_name": cells[0],
                            "default_value": _safe_text_value(default_match.group("value")),
                            "raw_value": default_match.group("value"),
                            "context_heading": heading,
                            "declaration_kind": "table",
                        },
                    )
                )
                break
        return entities

    @staticmethod
    def _inline_code_entities(
        line: str, *, file_path: str, line_number: int, heading: str
    ) -> list[DocEntity]:
        return [
            DocEntity(
                entity_type="inline_code",
                name=match.group(1),
                text=match.group(1),
                file_path=file_path,
                line_start=line_number,
                line_end=line_number,
                code_snippet=match.group(1),
                metadata={"context_heading": heading},
            )
            for match in _INLINE_CODE_RE.finditer(line)
        ]

    def _code_entities(
        self,
        lines: list[str],
        *,
        file_path: str,
        language: str,
        fence_start: int,
        fence_end: int,
        heading: str,
        closed: bool = True,
    ) -> list[DocEntity]:
        snippet = "\n".join(lines)
        entities = [
            DocEntity(
                entity_type="code_block",
                name=language or f"code-block@{fence_start}",
                text=snippet,
                file_path=file_path,
                line_start=fence_start,
                line_end=fence_end,
                code_snippet=snippet,
                metadata={
                    "language": language,
                    "context_heading": heading,
                    "content_line_start": fence_start + 1,
                    "closed": closed,
                },
            )
        ]
        if language in {"", "python", "py"}:
            entities.extend(
                self._python_call_entities(
                    snippet,
                    file_path=file_path,
                    content_start=fence_start + 1,
                    heading=heading,
                )
            )
        if language in {"", "bash", "sh", "shell", "console", "powershell", "ps1"}:
            entities.extend(
                self._cli_entities(
                    lines,
                    file_path=file_path,
                    content_start=fence_start + 1,
                    heading=heading,
                )
            )
        if language in {"json", "yaml", "yml", "toml"}:
            entities.extend(
                self._config_entities(
                    snippet,
                    file_path=file_path,
                    format_name=language,
                    content_start=fence_start + 1,
                    heading=heading,
                )
            )
        return entities

    @staticmethod
    def _config_entities(
        snippet: str,
        *,
        file_path: str,
        format_name: str,
        content_start: int,
        heading: str,
    ) -> list[DocEntity]:
        try:
            facts = ConfigParser().parse(
                snippet,
                format_name=format_name,
                file_path=file_path,
                line_offset=content_start - 1,
            )
        except ValueError:
            return []
        return [
            DocEntity(
                entity_type="config_key",
                name=fact.qualified_name,
                text=fact.qualified_name,
                file_path=file_path,
                line_start=fact.line_start,
                line_end=fact.line_end,
                code_snippet=fact.qualified_name,
                metadata={
                    **fact.metadata,
                    "context_heading": heading,
                    "source_kind": "fenced_config_block",
                },
            )
            for fact in facts
        ]

    @staticmethod
    def _python_call_entities(
        snippet: str, *, file_path: str, content_start: int, heading: str
    ) -> list[DocEntity]:
        try:
            tree = ast.parse(snippet)
        except SyntaxError:
            return []
        entities: list[DocEntity] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            arguments: list[dict[str, Any]] = []
            has_starred_arguments = False
            for index, argument in enumerate(node.args):
                if isinstance(argument, ast.Starred):
                    has_starred_arguments = True
                value = _safe_expression(argument)
                arguments.append({"kind": "positional", "position": index, "value": value})
            keyword_parameters: list[str] = []
            has_keyword_unpacking = False
            for keyword in node.keywords:
                name = keyword.arg or "**"
                if keyword.arg is None:
                    has_keyword_unpacking = True
                arguments.append(
                    {"kind": "keyword", "name": name, "value": _safe_expression(keyword.value)}
                )
                if keyword.arg:
                    keyword_parameters.append(keyword.arg)
            call_name = _call_name(node.func)
            source = ast.get_source_segment(snippet, node) or ast.unparse(node)
            entities.append(
                DocEntity(
                    entity_type="function_call",
                    name=call_name,
                    text=source,
                    file_path=file_path,
                    line_start=content_start + node.lineno - 1,
                    line_end=content_start + (node.end_lineno or node.lineno) - 1,
                    code_snippet=source,
                    metadata={
                        "context_heading": heading,
                        "arguments": arguments,
                        "keyword_parameters": keyword_parameters,
                        "has_starred_arguments": has_starred_arguments,
                        "has_keyword_unpacking": has_keyword_unpacking,
                    },
                )
            )
        return entities

    @staticmethod
    def _cli_entities(
        lines: list[str], *, file_path: str, content_start: int, heading: str
    ) -> list[DocEntity]:
        entities: list[DocEntity] = []
        for offset, original in enumerate(lines):
            command = original.strip()
            if command.startswith(("$ ", "> ")):
                command = command[2:].strip()
            looks_like_command = command.startswith(
                ("python ", "python3 ", "py ", "docsync-ai ", "pip ", "uv ")
            )
            if not command or not (looks_like_command or "--" in command):
                continue
            line_number = content_start + offset
            entities.append(
                DocEntity(
                    entity_type="cli_command",
                    name=command.split(maxsplit=1)[0],
                    text=command,
                    file_path=file_path,
                    line_start=line_number,
                    line_end=line_number,
                    code_snippet=command,
                    metadata={
                        "context_heading": heading,
                        "source_kind": "fenced_cli_command",
                        "script_name": MarkdownParser._script_name(command),
                    },
                )
            )
            for match in _CLI_FLAG_RE.finditer(command):
                value = _safe_text_value(match.group(2)) if match.group(2) else None
                entities.append(
                    DocEntity(
                        entity_type="cli_argument",
                        name=match.group(1),
                        text=match.group(0),
                        file_path=file_path,
                        line_start=line_number,
                        line_end=line_number,
                        code_snippet=match.group(0),
                        metadata={
                            "context_heading": heading,
                            "value": value,
                            "source_kind": "fenced_cli_command",
                            "script_name": MarkdownParser._script_name(command),
                        },
                    )
                )
        return entities

    @staticmethod
    def _script_name(command: str) -> str:
        parts = command.split()
        for index, part in enumerate(parts):
            if part.casefold() in {"python", "python3", "py"} and index + 1 < len(parts):
                return Path(parts[index + 1]).stem
        return ""


def parse_markdown_file(file_path: str | Path) -> list[DocEntity]:
    return MarkdownParser().parse_file(file_path)
