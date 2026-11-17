"""FastAPI 主服务的冒烟测试：不起浏览器、不连外网，只验证 HTTP 契约。"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from boss.app import app

    # with 语句会跑 startup 事件（清库、建锁），和真实启动路径一致
    with TestClient(app) as test_client:
        yield test_client


def test_health_and_status(client):
    assert client.get("/api/health").json()["status"] == "ok"

    status = client.get("/api/status").json()
    assert status["browser_running"] is False  # 测试环境没起浏览器
    assert "daily_stats" in status


def test_stats_and_doctor(client):
    stats = client.get("/api/stats").json()
    assert stats["today_applications"] == 0

    doctor = client.get("/api/doctor").json()
    assert doctor["checks"]["python"]["ok"] is True
    assert doctor["checks"]["browser"]["ok"] is False


def test_settings_put_then_get(client):
    resp = client.put(
        "/api/settings",
        json={
            "default_city": "广州",
            "siliconflow_api_key": "sk-siliconflow-test",
            "embedding_model": "BAAI/bge-m3",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["updated"]["default_city"] == "广州"

    settings = client.get("/api/settings").json()["settings"]
    assert settings["default_city"] == "广州"
    assert settings["siliconflow_api_key"] == "sk-siliconflow-test"
    assert settings["embedding_model"] == "BAAI/bge-m3"
    # 前端靠这个字段判断是否已配置 Key
    assert settings["ai_key_configured"] == "false"


def test_settings_put_ignores_empty_values(client):
    client.put("/api/settings", json={"default_city": "北京"})
    client.put("/api/settings", json={"default_city": ""})  # 空串不覆盖已有值
    assert client.get("/api/settings").json()["settings"]["default_city"] == "北京"


def test_agent_tools_schema(client):
    tools = client.get("/api/agent/tools").json()["tools"]
    assert tools, "Agent 工具列表不能为空"

    names = {tool["name"] for tool in tools}
    assert {"search_jobs", "apply_job", "smart_scan"} <= names
    for tool in tools:
        assert tool["description"]
        assert tool["parameters"]["type"] == "object"


def test_mock_and_token_endpoints(client):
    mocks = client.get("/api/mock/list").json()
    assert mocks["ok"] is True
    assert mocks["data"] == []

    stats = client.get("/api/llm-stats").json()
    assert "total_tokens" in stats["summary"]
    assert stats["recent"] == []


def test_dashboard_page_and_assets(client):
    page = client.get("/")
    assert page.status_code == 200
    assert "dashboard" in page.text.lower() or "BOSS" in page.text

    for asset in ("/static/css/style.css", "/static/js/app.js"):
        assert client.get(asset).status_code == 200
