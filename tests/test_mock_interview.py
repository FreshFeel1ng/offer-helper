"""模拟面试 WebSocket 全流程（假 LLM）：配置 → 出题 → 回答评分 → 标准答案 → 报告。

不联网、不起浏览器，覆盖 interview 服务里最容易回归的那段交互。
"""

import json

import pytest
from fastapi.testclient import TestClient

QUESTION = "请说说你在项目里负责的模块，以及遇到的最大技术难点。"
EVALUATION = {
    "score": 8,
    "correctness": "准确",
    "depth": "有细节",
    "comfort": None,
    "communication": "表达清晰",
    "comment": "回答到位，可以再补充量化结果",
}
STANDARD_ANSWER = {
    "key_points": "讲清职责、技术选型与结果",
    "detailed_answer": "我负责数据迁移模块……",
    "bonus_tips": "补上迁移耗时与数据一致性指标",
}
REPORT = {
    "overall_score": 82,
    "summary": "整体表现不错",
    "strengths": ["基础扎实"],
    "weaknesses": ["深度不足"],
    "technical_score": 8,
    "communication_score": 7,
    "problem_solving_score": 8,
    "suggestion": "多准备项目细节的量化数据",
}


@pytest.fixture
def interview_client(monkeypatch):
    import main as interview_main  # interview/main.py（conftest 已把 interview/ 加进 sys.path）
    from assistant import llm_client

    answers = [
        QUESTION,
        json.dumps(EVALUATION, ensure_ascii=False),
        json.dumps(STANDARD_ANSWER, ensure_ascii=False),
        json.dumps(REPORT, ensure_ascii=False),
    ]
    calls = []

    async def fake_achat(messages, temperature=0.3, max_tokens=None, model=None):
        calls.append(messages)
        return answers[min(len(calls) - 1, len(answers) - 1)]

    monkeypatch.setattr(llm_client, "achat", fake_achat)
    with TestClient(interview_main.app) as client:
        yield client, calls


def test_mock_interview_full_flow(interview_client, state):
    client, calls = interview_client

    with client.websocket_connect("/ws/mock") as ws:
        ws.send_text(
            json.dumps(
                {
                    "type": "configure",
                    "payload": {
                        "position": "后端",
                        "topic": "综合",
                        "difficulty": "hard",
                        "max_rounds": 1,
                    },
                }
            )
        )
        configured = ws.receive_json()
        assert configured["type"] == "configured"
        assert configured["payload"]["max_rounds"] == 1

        ws.send_text(json.dumps({"type": "start"}))
        question = ws.receive_json()
        assert question["type"] == "question"
        assert question["payload"]["question"] == QUESTION
        assert question["payload"]["round"] == 1

        ws.send_text(json.dumps({"type": "answer", "payload": {"text": "我负责数据迁移模块"}}))
        assert ws.receive_json()["type"] == "evaluating"

        evaluation = ws.receive_json()
        assert evaluation["type"] == "evaluation"
        assert evaluation["payload"]["score"] == 8

        standard = ws.receive_json()
        assert standard["type"] == "standard_answer"
        assert standard["payload"]["key_points"] == STANDARD_ANSWER["key_points"]

        ws.send_text(json.dumps({"type": "report"}))
        assert ws.receive_json()["type"] == "evaluating"

        report = ws.receive_json()
        assert report["type"] == "report"
        assert report["payload"]["overall_score"] == 82

        ws.send_text(json.dumps({"type": "ping"}))
        assert ws.receive_json()["type"] == "pong"

    # 报告落库（Web 端 /api/mock/list 依赖它）
    records = state.list_mock_interviews()
    assert len(records) == 1
    assert records[0]["score"] == 82
    assert records[0]["rounds"] == 1
    assert len(calls) == 4  # 出题 / 评分 / 标准答案 / 报告


def test_mock_interview_rejects_empty_answer(interview_client):
    client, _ = interview_client

    with client.websocket_connect("/ws/mock") as ws:
        ws.send_text(json.dumps({"type": "configure", "payload": {"max_rounds": 1}}))
        ws.receive_json()
        ws.send_text(json.dumps({"type": "start"}))
        ws.receive_json()

        ws.send_text(json.dumps({"type": "answer", "payload": {"text": "   "}}))
        error = ws.receive_json()
        assert error["type"] == "error"
        assert "不能为空" in error["payload"]["message"]


def test_mock_interview_requires_configuration(interview_client):
    client, _ = interview_client

    with client.websocket_connect("/ws/mock") as ws:
        ws.send_text(json.dumps({"type": "start"}))
        error = ws.receive_json()
        assert error["type"] == "error"
        assert "配置" in error["payload"]["message"]
