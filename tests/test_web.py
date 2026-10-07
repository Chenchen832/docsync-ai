import json

import pytest
from fastapi.testclient import TestClient

from docsync_ai.web.app import app, report_store
from docsync_ai.web.services import UserInputError, validate_git_url


@pytest.fixture(autouse=True)
def _clear_report_store():
    report_store.clear()
    yield
    report_store.clear()


@pytest.fixture
def client():
    return TestClient(app)


def _run_demo(client, *, ai_option="off"):
    response = client.post(
        "/analyze",
        data={"input_source": "demo", "ai_option": ai_option},
        follow_redirects=False,
    )
    assert response.status_code == 303
    return response.headers["location"]


def test_home_page_returns_200_and_has_demo_action(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "代码—文档一致性" in response.text
    assert "体验示例检测" in response.text
    assert "Demo / Mock" in response.text


def test_demo_analysis_renders_result_overview(client):
    result_url = _run_demo(client)

    response = client.get(result_url)

    assert response.status_code == 200
    assert "检测结果总览" in response.text
    assert "Confirmed" in response.text
    assert ">5<" in response.text


def test_result_page_displays_ds001_through_ds005(client):
    response = client.get(_run_demo(client))

    for rule_id in ("DS001", "DS002", "DS003", "DS004", "DS005"):
        assert rule_id in response.text
    assert "命令行参数已过期或不存在" in response.text


def test_result_page_displays_semantic_candidates(client):
    response = client.get(_run_demo(client))

    assert "待语义确认" in response.text
    assert "data_path" in response.text
    assert "dataset_file" in response.text
    assert "待 AI 复核" in response.text


def test_ai_off_has_no_ai_summary(client):
    response = client.get(_run_demo(client, ai_option="off"))

    assert "AI Review</span>" not in response.text
    assert "AI 语义复核：<strong>关闭" in response.text


def test_mock_ai_mode_is_visibly_labeled_and_shows_all_outcomes(client):
    response = client.get(_run_demo(client, ai_option="mock"))

    assert response.status_code == 200
    assert "Demo / Mock，非真实模型" in response.text
    assert "AI 判断一致" in response.text
    assert "AI 判断不一致" in response.text
    assert "需要人工确认" in response.text
    assert "AI 升级 Finding" in response.text


def test_unconfigured_ai_shows_notice_without_server_error(client, monkeypatch):
    for name in ("DOCSYNC_AI_API_KEY", "DOCSYNC_AI_BASE_URL", "DOCSYNC_AI_MODEL"):
        monkeypatch.delenv(name, raising=False)

    response = client.get(_run_demo(client, ai_option="review"))

    assert response.status_code == 200
    assert "AI Provider 尚未配置" in response.text
    assert "确定性检测结果" in response.text


def test_json_export_returns_original_report(client):
    result_url = _run_demo(client)
    report_id = result_url.rsplit("/", 1)[-1]

    response = client.get(f"/results/{report_id}/export.json")
    payload = json.loads(response.text)

    assert response.status_code == 200
    assert payload["summary"]["confirmed_findings"] == 5
    assert "attachment" in response.headers["content-disposition"]


def test_markdown_export_is_human_readable(client):
    result_url = _run_demo(client)
    report_id = result_url.rsplit("/", 1)[-1]

    response = client.get(f"/results/{report_id}/export.md")

    assert response.status_code == 200
    assert "# DocSync-AI 检测报告" in response.text
    assert "## HIGH 风险" in response.text
    assert "修复建议" in response.text


def test_invalid_local_path_returns_understandable_400(client):
    response = client.post(
        "/analyze",
        data={"input_source": "local", "local_path": "Z:\\definitely-missing", "ai_option": "off"},
    )

    assert response.status_code == 400
    assert "does not exist" in response.text
    assert "Traceback" not in response.text


def test_file_path_instead_of_directory_returns_400(client, tmp_path):
    target = tmp_path / "not-a-directory.txt"
    target.write_text("x", encoding="utf-8")

    response = client.post(
        "/analyze",
        data={"input_source": "local", "local_path": str(target), "ai_option": "off"},
    )

    assert response.status_code == 400
    assert "not a directory" in response.text


def test_internal_error_does_not_expose_traceback(client, monkeypatch):
    def fail(**_kwargs):
        raise RuntimeError("private implementation detail")

    monkeypatch.setattr("docsync_ai.web.app.run_analysis", fail)
    response = client.post(
        "/analyze", data={"input_source": "demo", "ai_option": "off"}
    )

    assert response.status_code == 500
    assert "内部错误" in response.text
    assert "private implementation detail" not in response.text
    assert "Traceback" not in response.text


@pytest.mark.parametrize(
    "url",
    [
        "git@github.com:owner/repo.git",
        "http://github.com/owner/repo.git",
        "https://user:secret@github.com/owner/repo.git",
        "https://example.com/owner/repo.git",
    ],
)
def test_git_url_validation_rejects_unsafe_or_unsupported_urls(url):
    with pytest.raises(UserInputError):
        validate_git_url(url)


def test_git_url_validation_accepts_github_https():
    assert validate_git_url("https://github.com/owner/repo.git") == (
        "https://github.com/owner/repo.git"
    )


def test_missing_result_and_exports_return_404(client):
    assert client.get("/results/missing").status_code == 404
    assert client.get("/results/missing/export.json").status_code == 404
    assert client.get("/results/missing/export.md").status_code == 404
