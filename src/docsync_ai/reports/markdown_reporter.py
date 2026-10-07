"""Human-readable Markdown report export."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

RULE_LABELS = {
    "DS001": "参数名称不一致",
    "DS002": "默认值不一致",
    "DS003": "命令行参数已过期或不存在",
    "DS004": "配置项与实际配置不一致",
    "DS005": "文档中的函数调用方式已经失效",
}


def _fact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False)


def _location(value: dict[str, Any]) -> str:
    return f"{value.get('file_path', '')}:{value.get('line_start', '')}"


class MarkdownReporter:
    def dumps(self, report: dict[str, Any]) -> str:
        summary = report.get("summary", {})
        lines = [
            "# DocSync-AI 检测报告",
            "",
            f"- 项目路径：`{report.get('project_root', '')}`",
            f"- 检测时间：`{report.get('generated_at', '')}`",
            "- 分析方式：静态分析，不执行被分析项目代码",
            "",
            "## 扫描摘要",
            "",
            f"- 扫描文件：{summary.get('scanned_files', 0)}",
            f"- Python 文件：{summary.get('python_files', 0)}",
            f"- Markdown 文件：{summary.get('markdown_files', 0)}",
            f"- 配置文件：{summary.get('config_files', 0)}",
            f"- 代码实体：{summary.get('code_entities', 0)}",
            f"- 文档实体：{summary.get('doc_entities', 0)}",
            f"- Confirmed Findings：{summary.get('confirmed_findings', 0)}",
            f"- Semantic Candidates：{summary.get('semantic_candidates', 0)}",
            f"- HIGH / MEDIUM / LOW：{summary.get('severity', {}).get('HIGH', 0)} / "
            f"{summary.get('severity', {}).get('MEDIUM', 0)} / "
            f"{summary.get('severity', {}).get('LOW', 0)}",
            "",
        ]
        for severity in ("HIGH", "MEDIUM", "LOW"):
            findings = [
                item for item in report.get("findings", []) if item.get("severity") == severity
            ]
            if not findings:
                continue
            lines.extend([f"## {severity} 风险", ""])
            for item in findings:
                lines.extend(self._finding_lines(item))

        candidates = report.get("semantic_candidates", [])
        reviews = report.get("semantic_reviews", [])
        if candidates or reviews:
            lines.extend(["## AI 语义复核", ""])
            for review in reviews:
                snapshot = review.get("candidate_snapshot", {})
                lines.extend(
                    [
                        f"### {snapshot.get('doc_parameter', '语义候选')}",
                        "",
                        f"- 决策：`{review.get('decision', '')}`",
                        f"- 置信信息：{review.get('confidence')}",
                        f"- 最终状态：`{review.get('final_status', '')}`",
                        f"- 原因：{review.get('reason', '')}",
                        f"- 建议：{review.get('recommended_fix', '') or '无需修改或建议人工确认'}",
                        "",
                    ]
                )
            if candidates:
                lines.extend(["### 当前待确认项", ""])
                for item in candidates:
                    parameter = item.get("doc_fact", {}).get("documented_parameter", "")
                    lines.append(
                        f"- `{item.get('rule_id')}` {parameter}：`{item.get('status')}`"
                    )
                lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    @staticmethod
    def _finding_lines(item: dict[str, Any]) -> list[str]:
        rule_id = item.get("rule_id", "")
        return [
            f"### {rule_id} {RULE_LABELS.get(rule_id, item.get('issue_type', ''))}",
            "",
            f"- 类型：`{item.get('issue_type', '')}`",
            f"- 来源：`{item.get('source', '')}`",
            f"- 检测置信分：{item.get('confidence', '')}",
            f"- 代码位置：`{_location(item.get('code_location', {}))}`",
            f"- 文档位置：`{_location(item.get('doc_location', {}))}`",
            f"- 问题说明：{item.get('message', '')}",
            f"- 修复建议：{item.get('suggestion', '')}",
            "",
            "真实代码事实：",
            "",
            "```json",
            _fact(item.get("code_fact")),
            "```",
            "",
            "文档事实：",
            "",
            "```json",
            _fact(item.get("doc_fact")),
            "```",
            "",
        ]

    def write(self, report: dict[str, Any], output_path: str | Path) -> Path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.dumps(report), encoding="utf-8")
        return path
