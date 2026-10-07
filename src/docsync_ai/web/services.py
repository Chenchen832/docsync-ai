"""Web orchestration without duplicating analysis logic."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from docsync_ai.semantic import MockLLMProvider
from docsync_ai.services import analyze_project

PROJECT_ROOT = Path(r"D:\AI+开源主题赛\02_项目源码\docsync-ai")
DEMO_PROJECT = PROJECT_ROOT / "examples" / "demo_project"
TEMP_ROOT = Path(r"D:\AI+开源主题赛\99_临时文件")


class UserInputError(ValueError):
    """An error that is safe and useful to show to a Web user."""


@dataclass(slots=True)
class AnalysisRun:
    report: dict[str, Any]
    source_label: str
    ai_label: str
    notice: str = ""


class ReportStore:
    """Small process-local report store suitable for the local demo server."""

    def __init__(self) -> None:
        self._reports: dict[str, AnalysisRun] = {}
        self._lock = threading.Lock()

    def put(self, result: AnalysisRun) -> str:
        report_id = uuid4().hex
        with self._lock:
            self._reports[report_id] = result
        return report_id

    def get(self, report_id: str) -> AnalysisRun | None:
        with self._lock:
            return self._reports.get(report_id)

    def clear(self) -> None:
        with self._lock:
            self._reports.clear()


def validate_git_url(value: str) -> str:
    url = value.strip()
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise UserInputError("请输入不含凭据、查询参数或片段的 HTTPS Git 仓库地址。")
    if parsed.hostname.casefold() not in {"github.com", "gitlab.com", "gitee.com"}:
        raise UserInputError("当前仅支持 GitHub、GitLab 或 Gitee 的 HTTPS 仓库地址。")
    if not parsed.path.strip("/"):
        raise UserInputError("Git 仓库地址缺少仓库路径。")
    return url


def clone_repository(url: str) -> Path:
    safe_url = validate_git_url(url)
    TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    destination = Path(tempfile.mkdtemp(prefix="docsync_git_", dir=TEMP_ROOT))
    try:
        completed = subprocess.run(
            ["git", "clone", "--depth", "1", "--", safe_url, str(destination)],
            capture_output=True,
            check=False,
            encoding="utf-8",
            errors="replace",
            shell=False,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        _safe_cleanup(destination)
        raise UserInputError("Git 仓库导入失败，请检查网络、Git 安装和仓库地址。") from exc
    if completed.returncode != 0:
        _safe_cleanup(destination)
        raise UserInputError("Git clone 失败，请确认仓库可访问且地址正确。")
    return destination


def run_analysis(
    *,
    input_source: str,
    local_path: str,
    git_url: str,
    ai_option: str,
    keep_clone: bool = False,
) -> AnalysisRun:
    cloned_path: Path | None = None
    if input_source == "demo":
        project_path = DEMO_PROJECT
        source_label = "内置 Demo 项目"
    elif input_source == "local":
        if not local_path.strip():
            raise UserInputError("请输入本地项目目录。")
        project_path = Path(local_path.strip()).expanduser()
        source_label = str(project_path)
    elif input_source == "git":
        cloned_path = clone_repository(git_url)
        project_path = cloned_path
        source_label = git_url.strip()
    else:
        raise UserInputError("请选择本地项目、Git 仓库或示例项目。")

    if ai_option == "off":
        ai_mode = "off"
        provider = None
        ai_label = "关闭"
    elif ai_option == "review":
        ai_mode = "review"
        provider = None
        ai_label = "真实 Provider"
    elif ai_option == "mock":
        ai_mode = "review"
        provider = MockLLMProvider(["CONSISTENT", "INCONSISTENT", "UNCERTAIN"])
        ai_label = "Demo / Mock"
    else:
        raise UserInputError("未知的 AI 语义复核模式。")

    try:
        report = analyze_project(
            project_path,
            ai_mode=ai_mode,
            provider=provider,
            cache_path=TEMP_ROOT / "docsync_web_ai_cache.json",
        )
    except ValueError as exc:
        raise UserInputError(str(exc)) from exc
    finally:
        if cloned_path is not None and not keep_clone:
            _safe_cleanup(cloned_path)

    notice = ""
    if ai_option == "review" and report["ai_statistics"].get("provider") == "unavailable":
        notice = "AI Provider 尚未配置，本次仅保留确定性检测结果，语义候选已转人工确认。"
    return AnalysisRun(report=report, source_label=source_label, ai_label=ai_label, notice=notice)


def _safe_cleanup(path: Path) -> None:
    try:
        resolved = path.resolve()
        resolved.relative_to(TEMP_ROOT.resolve())
    except (OSError, ValueError):
        return
    if resolved.name.startswith("docsync_git_") and resolved.is_dir():
        try:
            shutil.rmtree(resolved, onerror=_remove_readonly)
        except OSError:
            # The scan result remains valid if Windows temporarily holds a Git file.
            return


def _remove_readonly(function, path: str, _error_info) -> None:
    os.chmod(path, stat.S_IWRITE)
    function(path)
