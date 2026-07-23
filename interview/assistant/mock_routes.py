"""
模拟面试 WebSocket 路由（独立文件，避免缩进混乱）
"""

import json
import uuid
from typing import Optional

from fastapi import WebSocket

from .mock import (
    MockInterviewSession,
    create_mock_session,
    delete_mock_session,
)


def register_mock_routes(app):
    """在 FastAPI app 上注册模拟面试 WebSocket 路由"""

    @app.websocket("/ws/mock")
    async def ws_mock_interview(websocket: WebSocket):
        print("[Mock面试] 收到 WebSocket 连接请求")
        await websocket.accept()
        msession: Optional[MockInterviewSession] = None
        session_id = str(uuid.uuid4())[:8]

        try:
            while True:
                raw = await websocket.receive_text()
                data = json.loads(raw)
                msg_type = data.get("type", "")

                if msg_type == "configure":
                    payload = data.get("payload", {})
                    msession = create_mock_session(
                        session_id=session_id,
                        position=payload.get("position", "全栈开发工程师"),
                        topic=payload.get("topic", "综合技术面试"),
                        difficulty=payload.get("difficulty", "medium"),
                        max_rounds=int(payload.get("max_rounds", 5)),
                    )
                    print(f"[Mock面试] 创建会话 {session_id}: {msession.position} ({msession.topic})")
                    await websocket.send_text(json.dumps(
                        {"type": "configured", "payload": msession.to_summary()}, ensure_ascii=False))

                elif msg_type == "start":
                    if not msession:
                        await websocket.send_text(json.dumps(
                            {"type": "error", "payload": {"message": "请先完成面试配置"}}, ensure_ascii=False))
                        continue
                    question = await msession.generate_question()
                    print(f"[Mock面试] 第{len(msession.qa_history)}题: {question[:50]}...")
                    await websocket.send_text(json.dumps(
                        {"type": "question", "payload": {"question": question,
                         "round": msession.round_num, "total": msession.max_rounds}}, ensure_ascii=False))

                elif msg_type == "answer":
                    if not msession:
                        await websocket.send_text(json.dumps(
                            {"type": "error", "payload": {"message": "没有活跃的面试"}}, ensure_ascii=False))
                        continue
                    answer = data.get("payload", {}).get("text", "")
                    if not answer.strip():
                        await websocket.send_text(json.dumps(
                            {"type": "error", "payload": {"message": "回答不能为空"}}, ensure_ascii=False))
                        continue
                    print(f"[Mock面试] 收到第{len(msession.qa_history)}题回答 ({len(answer)}字)")
                    await websocket.send_text(json.dumps(
                        {"type": "evaluating", "payload": {"message": "正在评估..."}}, ensure_ascii=False))
                    evaluation = await msession.evaluate_answer(answer)
                    print(f"[Mock面试] 评分: {evaluation.get('score', 0)}/10")
                    await websocket.send_text(json.dumps(
                        {"type": "evaluation", "payload": evaluation}, ensure_ascii=False))

                elif msg_type == "next":
                    if not msession:
                        await websocket.send_text(json.dumps(
                            {"type": "error", "payload": {"message": "没有活跃的面试"}}, ensure_ascii=False))
                        continue
                    if msession.STATUS == "finished":
                        await websocket.send_text(json.dumps(
                            {"type": "finished", "payload": {"message": "面试已完成"}}, ensure_ascii=False))
                        continue
                    question = await msession.generate_question()
                    print(f"[Mock面试] 第{len(msession.qa_history)}题: {question[:50]}...")
                    await websocket.send_text(json.dumps(
                        {"type": "question", "payload": {"question": question,
                         "round": msession.round_num, "total": msession.max_rounds}}, ensure_ascii=False))

                elif msg_type == "report":
                    if not msession:
                        await websocket.send_text(json.dumps(
                            {"type": "error", "payload": {"message": "没有活跃的面试"}}, ensure_ascii=False))
                        continue
                    await websocket.send_text(json.dumps(
                        {"type": "evaluating", "payload": {"message": "正在生成评估报告..."}}, ensure_ascii=False))
                    report = await msession.generate_report()
                    print(f"[Mock面试] 总评: {report.get('overall_score', 0)}/100")
                    try:
                        from boss.state import get_db
                        db = get_db()
                        cur = db.cursor()
                        cur.execute(
                            "INSERT INTO mock_interviews "
                            "(position, topic, difficulty, rounds, qa_json, score, "
                            "strengths, weaknesses, overall_evaluation) "
                            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                            (msession.position, msession.topic, msession.difficulty,
                             len(msession.qa_history),
                             json.dumps(msession.qa_history, ensure_ascii=False),
                             report.get("overall_score", 0),
                             json.dumps(report.get("strengths", []), ensure_ascii=False),
                             json.dumps(report.get("weaknesses", []), ensure_ascii=False),
                             json.dumps(report, ensure_ascii=False)))
                        db.commit()
                        cur.close()
                        print("[Mock面试] 报告已保存到数据库")
                    except Exception as e:
                        print(f"[Mock面试] 保存报告失败: {e}")
                    await websocket.send_text(json.dumps(
                        {"type": "report", "payload": report}, ensure_ascii=False))

                elif msg_type == "skip":
                    if not msession:
                        continue
                    if msession.qa_history:
                        msession.qa_history[-1]["a"] = "(跳过)"
                        msession.qa_history[-1]["score"] = 0
                    question = await msession.generate_question()
                    await websocket.send_text(json.dumps(
                        {"type": "question", "payload": {"question": question,
                         "round": msession.round_num, "total": msession.max_rounds}}, ensure_ascii=False))

                elif msg_type == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))

        except Exception as e:
            print(f"[Mock面试] WebSocket 异常: {e}")
            try:
                await websocket.close()
            except Exception:
                pass
        finally:
            if msession:
                delete_mock_session(session_id)
                print(f"[Mock面试] 会话 {session_id} 已清理")
