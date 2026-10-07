"""Single analysis workflow shared by every user interface."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from docsync_ai.aligners import EntityAligner
from docsync_ai.models import FindingStatus
from docsync_ai.parsers import ConfigParser, MarkdownParser, PythonParser, PythonSourceError
from docsync_ai.reports import JsonReporter
from docsync_ai.rules import (
    CallSignatureRule,
    CliOptionRule,
    ConfigKeyRule,
    DefaultValueRule,
    ParameterRule,
)
from docsync_ai.semantic import (
    AIStatistics,
    BaseLLMProvider,
    OpenAICompatibleProvider,
    ProviderConfigurationError,
    SemanticReviewCache,
    SemanticReviewEngine,
    unavailable_review_outcome,
)
from docsync_ai.semantic.config import SEMANTIC_REVIEW_THRESHOLD

_EXCLUDED_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "node_modules",
    "build",
    "dist",
    ".docsync-ai-cache",
}


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root)
    except (OSError, ValueError):
        return False
    return True


def _discover(root: Path, suffix: str) -> list[Path]:
    return sorted(
        path
        for path in root.rglob(f"*{suffix}")
        if path.is_file()
        and _is_within(path, root)
        and not any(part.casefold() in _EXCLUDED_DIRECTORIES for part in path.parts)
    )


def analyze_project(
    project_root: str | Path,
    *,
    ai_mode: str = "off",
    provider: BaseLLMProvider | None = None,
    cache_path: str | Path | None = None,
    semantic_threshold: float = SEMANTIC_REVIEW_THRESHOLD,
) -> dict[str, Any]:
    """Analyze a local project without importing or executing target code."""

    root = Path(project_root).expanduser().resolve()
    if not root.exists():
        raise ValueError(f"Project path does not exist: {root}")
    if not root.is_dir():
        raise ValueError(f"Project path is not a directory: {root}")
    if ai_mode not in {"off", "review"}:
        raise ValueError("AI mode must be 'off' or 'review'")

    python_files = _discover(root, ".py")
    markdown_files = _discover(root, ".md")
    config_files = [
        path
        for suffix in (".json", ".yaml", ".yml", ".toml")
        for path in _discover(root, suffix)
    ]
    code_entities = []
    doc_entities = []
    errors: list[dict[str, str]] = []
    warnings: list[str] = []
    if not python_files:
        warnings.append("未发现 Python 文件；与 Python 接口相关的检测将没有结果。")
    if not markdown_files:
        warnings.append("未发现 Markdown 文件；无法比较代码与 Markdown 文档。")

    python_parser = PythonParser()
    markdown_parser = MarkdownParser()
    config_parser = ConfigParser()
    for path in python_files:
        try:
            code_entities.extend(python_parser.parse_file(path))
        except PythonSourceError as exc:
            errors.append({"file_path": str(path), "error": str(exc)})
    for path in markdown_files:
        try:
            doc_entities.extend(markdown_parser.parse_file(path))
        except (OSError, UnicodeError) as exc:
            errors.append({"file_path": str(path), "error": f"Unable to read Markdown: {exc}"})
    for path in config_files:
        try:
            code_entities.extend(config_parser.parse_file(path))
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append({"file_path": str(path), "error": f"Unable to parse config: {exc}"})

    findings = []
    findings.extend(ParameterRule().check(code_entities, doc_entities))
    findings.extend(DefaultValueRule().check(code_entities, doc_entities))
    findings.extend(CliOptionRule().check(code_entities, doc_entities))
    findings.extend(ConfigKeyRule().check(code_entities, doc_entities))
    findings.extend(CallSignatureRule().check(code_entities, doc_entities))
    findings.sort(
        key=lambda item: (
            item.code_location.file_path,
            item.code_location.line_start,
            item.rule_id,
            item.doc_location.line_start,
        )
    )

    scanned = [str(path) for path in [*python_files, *markdown_files, *config_files]]
    alignments = EntityAligner().align(code_entities, doc_entities)
    confirmed = [item for item in findings if item.status == FindingStatus.CONFIRMED]
    candidates = [item for item in findings if item.status != FindingStatus.CONFIRMED]
    semantic_reviews = []
    ai_statistics = AIStatistics(
        enabled=False,
        provider=None,
        model=None,
        candidate_count=len(candidates),
    )
    if ai_mode == "review":
        try:
            active_provider = provider or OpenAICompatibleProvider.from_env()
        except ProviderConfigurationError as exc:
            outcome = unavailable_review_outcome(candidates, reason=str(exc))
            errors.append({"file_path": "AI semantic review", "error": str(exc)})
        else:
            cache = SemanticReviewCache(
                cache_path or root / ".docsync-ai-cache" / "semantic_reviews.json"
            )
            outcome = SemanticReviewEngine(
                active_provider,
                cache=cache,
                threshold=semantic_threshold,
            ).review(candidates)
        confirmed.extend(outcome.promoted_findings)
        candidates = outcome.remaining_candidates
        semantic_reviews = outcome.reviews
        ai_statistics = outcome.statistics

    report = JsonReporter().build(
        [*confirmed, *candidates],
        code_entities=code_entities,
        doc_entities=doc_entities,
        scanned_files=scanned,
        project_root=str(root),
        alignments=alignments,
        semantic_reviews=semantic_reviews,
        ai_statistics=ai_statistics,
    )
    report["summary"].update(
        {
            "python_files": len(python_files),
            "markdown_files": len(markdown_files),
            "config_files": len(config_files),
        }
    )
    report["analysis_errors"] = errors
    report["analysis_warnings"] = warnings
    return report
