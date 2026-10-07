"""FastAPI application for the local Phase 4 demo."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from urllib.parse import parse_qs

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from docsync_ai.reports import JsonReporter, MarkdownReporter
from docsync_ai.web.services import DEMO_PROJECT, ReportStore, UserInputError, run_analysis

LOGGER = logging.getLogger(__name__)
WEB_ROOT = Path(__file__).parent
RULE_LABELS = {
    "DS001": "参数名称不一致",
    "DS002": "默认值不一致",
    "DS003": "命令行参数已过期或不存在",
    "DS004": "配置项与实际配置不一致",
    "DS005": "文档中的函数调用方式已经失效",
}
STATUS_LABELS = {
    "NEEDS_SEMANTIC_REVIEW": "待 AI 复核",
    "RESOLVED_CONSISTENT": "AI 判断一致",
    "CONFIRMED": "AI 判断不一致",
    "NEEDS_MANUAL_REVIEW": "需要人工确认",
}

app = FastAPI(title="DocSync-AI", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=WEB_ROOT / "static"), name="static")
templates = Jinja2Templates(directory=WEB_ROOT / "templates")
report_store = ReportStore()


async def _form_values(request: Request) -> dict[str, str]:
    body = (await request.body()).decode("utf-8", errors="replace")
    parsed = parse_qs(body, keep_blank_values=True)
    return {name: values[-1] for name, values in parsed.items() if values}


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"demo_path": str(DEMO_PROJECT)},
    )


@app.post("/analyze")
async def analyze(request: Request) -> Response:
    values = await _form_values(request)
    try:
        result = run_analysis(
            input_source=values.get("input_source", "local"),
            local_path=values.get("local_path", ""),
            git_url=values.get("git_url", ""),
            ai_option=values.get("ai_option", "off"),
            keep_clone=values.get("keep_clone") == "on",
        )
    except UserInputError as exc:
        return templates.TemplateResponse(
            request=request,
            name="error.html",
            context={"title": "无法开始检测", "message": str(exc)},
            status_code=400,
        )
    except Exception:
        LOGGER.exception("Unexpected Web analysis failure")
        return templates.TemplateResponse(
            request=request,
            name="error.html",
            context={
                "title": "检测过程中出现内部错误",
                "message": "请检查项目路径和文件内容后重试。详细信息已记录在开发日志中。",
            },
            status_code=500,
        )
    report_id = report_store.put(result)
    return RedirectResponse(url=f"/results/{report_id}", status_code=303)


@app.get("/results/{report_id}", response_class=HTMLResponse)
async def result_page(request: Request, report_id: str) -> HTMLResponse:
    stored = report_store.get(report_id)
    if stored is None:
        return templates.TemplateResponse(
            request=request,
            name="error.html",
            context={"title": "结果不存在", "message": "该结果已失效，请重新运行检测。"},
            status_code=404,
        )
    reviews = stored.report.get("semantic_reviews", [])
    ai_counts = {
        "reviews": len(reviews),
        "resolved": sum(item.get("final_status") == "RESOLVED_CONSISTENT" for item in reviews),
        "promoted": sum(item.get("final_status") == "CONFIRMED" for item in reviews),
        "manual": sum(
            item.get("final_status") == "NEEDS_MANUAL_REVIEW" for item in reviews
        ),
    }
    return templates.TemplateResponse(
        request=request,
        name="result.html",
        context={
            "report_id": report_id,
            "result": stored,
            "report": stored.report,
            "rule_labels": RULE_LABELS,
            "status_labels": STATUS_LABELS,
            "ai_counts": ai_counts,
            "focus": request.query_params.get("focus", ""),
            "json_dump": lambda value: json.dumps(value, ensure_ascii=False, indent=2),
        },
    )


@app.get("/results/{report_id}/export.json")
async def export_json(report_id: str) -> Response:
    stored = report_store.get(report_id)
    if stored is None:
        return Response("Result not found", status_code=404, media_type="text/plain")
    content = JsonReporter().dumps(stored.report) + "\n"
    return Response(
        content,
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="docsync-ai-report.json"'},
    )


@app.get("/results/{report_id}/export.md")
async def export_markdown(report_id: str) -> Response:
    stored = report_store.get(report_id)
    if stored is None:
        return Response("Result not found", status_code=404, media_type="text/plain")
    return Response(
        MarkdownReporter().dumps(stored.report),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="docsync-ai-report.md"'},
    )


def run_web(*, host: str = "127.0.0.1", port: int = 8000) -> None:
    print(f"DocSync-AI Web: http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run_web()
