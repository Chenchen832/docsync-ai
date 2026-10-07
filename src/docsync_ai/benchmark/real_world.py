"""Small real-world Git case study runner for Phase 5."""

from __future__ import annotations

import subprocess
import time
from datetime import date
from pathlib import Path
from typing import Any

from docsync_ai.services import analyze_project
from docsync_ai.web.services import TEMP_ROOT, _safe_cleanup, clone_repository


def run_real_world_case(
    *,
    repository_url: str,
    project_name: str,
    expected_license: str,
    license_evidence: str | None = None,
    output_path: str | Path,
) -> dict[str, Any]:
    started = time.perf_counter()
    cloned = clone_repository(repository_url)
    try:
        commit = _git_commit(cloned)
        license_file, license_text = _license_text(cloned)
        expected_text = license_evidence or expected_license
        license_verified = expected_text.casefold() in license_text.casefold()
        report = analyze_project(cloned, ai_mode="off")
        elapsed_ms = (time.perf_counter() - started) * 1000
        result = {
            "project_name": project_name,
            "repository_url": repository_url,
            "commit": commit,
            "expected_license": expected_license,
            "license_file": str(license_file.relative_to(cloned)) if license_file else "NOT FOUND",
            "license_verified": license_verified,
            "test_date": date.today().isoformat(),
            "temporary_clone_path": str(cloned),
            "temporary_root_verified": _is_within_temp(cloned),
            "analysis_time_ms": round(elapsed_ms, 3),
            "summary": report["summary"],
            "analysis_error_count": len(report["analysis_errors"]),
            "findings": [
                {
                    "rule_id": item["rule_id"],
                    "severity": item["severity"],
                    "message": item["message"],
                }
                for item in report["findings"]
            ],
        }
        Path(output_path).write_text(_markdown(result), encoding="utf-8")
        return result
    finally:
        _safe_cleanup(cloned)


def _git_commit(repository: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        capture_output=True,
        check=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
    )
    return completed.stdout.strip()


def _license_text(repository: Path) -> tuple[Path | None, str]:
    for pattern in ("LICENSE*", "COPYING*"):
        for path in sorted(repository.glob(pattern)):
            if path.is_file():
                return path, path.read_text(encoding="utf-8", errors="replace")[:20000]
    return None, ""


def _is_within_temp(path: Path) -> bool:
    try:
        path.resolve().relative_to(TEMP_ROOT.resolve())
    except (OSError, ValueError):
        return False
    return True


def _markdown(result: dict[str, Any]) -> str:
    summary = result["summary"]
    lines = [
        "# Phase 5 真实项目测试",
        "",
        f"- 项目：{result['project_name']}",
        f"- 仓库：{result['repository_url']}",
        f"- 测试 commit：`{result['commit']}`",
        f"- 许可证：{result['expected_license']}",
        f"- 许可证文件：`{result['license_file']}`",
        f"- 许可证核验：{'通过' if result['license_verified'] else '未通过'}",
        f"- 测试日期：{result['test_date']}",
        f"- 临时 clone 路径：`{result['temporary_clone_path']}`",
        f"- 位于指定临时目录：{'是' if result['temporary_root_verified'] else '否'}",
        f"- 分析耗时：{result['analysis_time_ms']:.3f} ms",
        "",
        "## 分析结果",
        "",
        f"- 扫描文件：{summary['scanned_files']}",
        f"- Python 文件：{summary['python_files']}",
        f"- Markdown 文件：{summary['markdown_files']}",
        f"- 配置文件：{summary['config_files']}",
        f"- Confirmed Findings：{summary['confirmed_findings']}",
        f"- Semantic Candidates：{summary['semantic_candidates']}",
        f"- 文件解析错误：{result['analysis_error_count']}",
        "",
        "## Findings 人工抽查清单",
        "",
    ]
    if result["findings"]:
        for finding in result["findings"]:
            lines.append(
                f"- `{finding['rule_id']}` / {finding['severity']}：{finding['message']}"
            )
    else:
        lines.append("本次扫描没有输出 Confirmed Finding；该结果仅说明系统可稳定处理此真实仓库。")
    lines.extend(
        [
            "",
            "## 说明",
            "",
            (
                "该项目只用于 Real-world Case Study，不计入 controlled benchmark 的 "
                "Precision、Recall 或 F1。"
            ),
            "分析过程未执行仓库代码、安装脚本或 README 命令。分析完成后临时 clone 已清理。",
            "",
        ]
    )
    return "\n".join(lines)
