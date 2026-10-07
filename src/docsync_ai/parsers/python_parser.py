"""Python AST parser.

The parser never imports or executes the analyzed project. All facts come from
``ast.parse`` and literal-safe AST inspection.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from docsync_ai.models import CodeEntity


class PythonSourceError(ValueError):
    """Raised when a Python file cannot be decoded or parsed."""


def _safe_value(node: ast.AST | None) -> Any:
    if node is None:
        return None
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return ast.unparse(node)
    if isinstance(value, tuple):
        return [_make_json_safe(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_make_json_safe(item) for item in value), key=repr)
    return _make_json_safe(value)


def _make_json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _make_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_make_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _annotation(node: ast.AST | None) -> str | None:
    return ast.unparse(node) if node is not None else None


class _EntityVisitor(ast.NodeVisitor):
    def __init__(self, file_path: str, module_name: str, source: str) -> None:
        self.file_path = file_path
        self.module_name = module_name
        self.source = source
        self.entities: list[CodeEntity] = []
        self.context: list[tuple[str, str]] = []

    def _qualified(self, name: str) -> str:
        parts = [self.module_name, *(item[1] for item in self.context), name]
        return ".".join(part for part in parts if part)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.entities.append(
            CodeEntity(
                entity_type="class",
                name=node.name,
                qualified_name=self._qualified(node.name),
                file_path=self.file_path,
                line_start=node.lineno,
                line_end=node.end_lineno or node.lineno,
                description=ast.get_docstring(node, clean=True) or "",
                metadata={
                    "bases": [ast.unparse(base) for base in node.bases],
                    "decorators": [ast.unparse(item) for item in node.decorator_list],
                },
            )
        )
        self.context.append(("class", node.name))
        self.generic_visit(node)
        self.context.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node, is_async=False)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node, is_async=True)

    def _visit_function(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, *, is_async: bool
    ) -> None:
        parameters, defaults, parameter_kinds = self._signature(node.args)
        is_method = bool(self.context and self.context[-1][0] == "class")
        self.entities.append(
            CodeEntity(
                entity_type="method"
                if is_method
                else ("async_function" if is_async else "function"),
                name=node.name,
                qualified_name=self._qualified(node.name),
                file_path=self.file_path,
                line_start=node.lineno,
                line_end=node.end_lineno or node.lineno,
                parameters=parameters,
                default_values=defaults,
                description=ast.get_docstring(node, clean=True) or "",
                metadata={
                    "is_async": is_async,
                    "return_annotation": _annotation(node.returns),
                    "decorators": [ast.unparse(item) for item in node.decorator_list],
                    "parameter_kinds": parameter_kinds,
                },
            )
        )
        self.context.append(("function", node.name))
        self.generic_visit(node)
        self.context.pop()

    @staticmethod
    def _signature(args: ast.arguments) -> tuple[list[str], dict[str, Any], dict[str, str]]:
        positional = [*args.posonlyargs, *args.args]
        parameters = [item.arg for item in positional]
        kinds: dict[str, str] = {item.arg: "positional_only" for item in args.posonlyargs}
        kinds.update({item.arg: "positional_or_keyword" for item in args.args})
        defaults: dict[str, Any] = {}

        if args.defaults:
            for argument, default in zip(
                positional[-len(args.defaults) :], args.defaults, strict=True
            ):
                defaults[argument.arg] = _safe_value(default)

        if args.vararg:
            parameters.append(f"*{args.vararg.arg}")
            kinds[args.vararg.arg] = "var_positional"

        for argument, default in zip(args.kwonlyargs, args.kw_defaults, strict=True):
            parameters.append(argument.arg)
            kinds[argument.arg] = "keyword_only"
            if default is not None:
                defaults[argument.arg] = _safe_value(default)

        if args.kwarg:
            parameters.append(f"**{args.kwarg.arg}")
            kinds[args.kwarg.arg] = "var_keyword"

        return parameters, defaults, kinds

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute) and node.func.attr == "add_argument":
            parser_name = ast.unparse(node.func.value)
            option_strings = [
                item.value
                for item in node.args
                if isinstance(item, ast.Constant) and isinstance(item.value, str)
            ]
            if option_strings:
                name = next(
                    (item for item in option_strings if item.startswith("--")), option_strings[0]
                )
                keywords = {item.arg: item.value for item in node.keywords if item.arg}
                default_values = (
                    {name: _safe_value(keywords["default"])} if "default" in keywords else {}
                )
                self.entities.append(
                    CodeEntity(
                        entity_type="cli_argument",
                        name=name,
                        qualified_name=self._qualified(name),
                        file_path=self.file_path,
                        line_start=node.lineno,
                        line_end=node.end_lineno or node.lineno,
                        default_values=default_values,
                        description=(
                            str(_safe_value(keywords["help"])) if "help" in keywords else ""
                        ),
                        metadata={
                            "option_strings": option_strings,
                            "parser_name": parser_name,
                            "parser_context": ".".join(item[1] for item in self.context),
                            "dest": _safe_value(keywords.get("dest")),
                            "type": _annotation(keywords.get("type")),
                            "required": _safe_value(keywords.get("required")),
                            "choices": _safe_value(keywords.get("choices")),
                            "action": _safe_value(keywords.get("action")),
                        },
                    )
                )
        self.generic_visit(node)


class PythonParser:
    """Extract normalized entities from Python source without executing it."""

    def parse_file(self, file_path: str | Path) -> list[CodeEntity]:
        path = Path(file_path)
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise PythonSourceError(f"Unable to read {path}: {exc}") from exc
        return self.parse(source, file_path=str(path))

    def parse(self, source: str, *, file_path: str = "<memory>") -> list[CodeEntity]:
        try:
            tree = ast.parse(source, filename=file_path)
        except SyntaxError as exc:
            raise PythonSourceError(
                f"Unable to parse {file_path} at line {exc.lineno}: {exc.msg}"
            ) from exc

        path = Path(file_path)
        module_name = path.stem if file_path != "<memory>" else "memory"
        line_count = max(1, len(source.splitlines()))
        visitor = _EntityVisitor(file_path, module_name, source)
        visitor.entities.append(
            CodeEntity(
                entity_type="module",
                name=module_name,
                qualified_name=module_name,
                file_path=file_path,
                line_start=1,
                line_end=line_count,
                description=ast.get_docstring(tree, clean=True) or "",
            )
        )
        visitor.visit(tree)
        return visitor.entities


def parse_python_file(file_path: str | Path) -> list[CodeEntity]:
    return PythonParser().parse_file(file_path)
