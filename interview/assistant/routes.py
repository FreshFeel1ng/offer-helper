"""
面试辅助 WebSocket 路由

集成到 offer-helper 的 interview 服务中，提供:
- 实时面试辅助（语音识别 → 问题检测 → AI回答生成）
- 简历上传与RAG检索
- 系统音频捕获
"""
import asyncio
import uuid
import json
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, File, UploadFile, Form, HTTPException
from pydantic import BaseModel

from .config import config
from .agent import InterviewAgent
from .speech import preprocess_transcript, is_complete_question, extract_question
from .audio_capture import SystemAudioCapture, WhisperTranscriber
from .resume import ResumeKnowledgeBase
from .mock import (
    MockInterviewSession,
    create_mock_session,
    delete_mock_session,
)


class SessionConfig(BaseModel):
    interview_type: str = "技术面试"
    candidate_background: str = "全栈开发工程师"
    language: str = "zh"
    temperature: float = 0.7
    max_tokens: int = 500
    model: str = "deepseek-chat"


class AssistantSessionManager:
    """管理 Agent 会话，限制只允许一个活跃连接"""

    def __init__(self):
        self.sessions: dict[str, dict] = {}
        self.active_ws: dict = {}

    def create_session(self, cfg: Optional[SessionConfig] = None) -> dict:
        """创建新会话"""
        # 关闭所有旧连接
        old_ws_list = list(self.active_ws.keys())
        for old_ws in old_ws_list:
            try:
                old_ws.close()
            except Exception:
                pass

        # 清理所有旧 session
        old_ids = list(self.sessions.keys())
        for sid in old_ids:
            s = self.sessions.pop(sid, None)
            if s and s.get("audio_capture"):
                try:
                    s["audio_capture"].stop()
                except Exception:
                    pass

        session_id = "default"
        agent = InterviewAgent()
        resume_kb = ResumeKnowledgeBase(session_id=session_id)
        loaded = resume_kb.load_latest()
        if loaded:
            agent.resume_kb = resume_kb

        session = {
            "id": session_id,
            "agent": agent,
            "config": cfg or SessionConfig(),
            "resume_kb": resume_kb,
        }
        self.sessions[session_id] = session
        print(f"[AssistantSession] 创建会话, 简历: {'已加载' if loaded else '未上传'}")
        return session

    def get_session(self, session_id: str) -> Optional[dict]:
        return self.sessions.get(session_id)

    def remove_session(self, session_id: str):
        self.sessions.pop(session_id, None)

    def get_all_sessions(self) -> list[dict]:
        return list(self.sessions.values())


assistant_manager = AssistantSessionManager()


def register_assistant_routes(app: FastAPI):
    """将面试辅助路由注册到 FastAPI 应用"""

    # ============ REST API ============

    @app.get("/api/assistant/health")
    async def assistant_health():
        return {"status": "ok", "sessions": len(assistant_manager.sessions)}

    @app.post("/api/assistant/sessions")
    async def create_assistant_session(cfg: Optional[SessionConfig] = None):
        session = assistant_manager.create_session(cfg)
        return {"sessionId": session["id"], "config": session["config"].model_dump()}

    @app.post("/api/assistant/resume/upload")
    async def upload_resume(
        file: UploadFile = File(...),
        sessionId: str = Form(""),
    ):
        """上传简历文件（PDF/DOCX/TXT）"""
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="文件为空")

        session = assistant_manager.get_session(sessionId) if sessionId else None
        if session:
            resume_kb = session["resume_kb"]
        else:
            resume_kb = ResumeKnowledgeBase()

        try:
            resume = resume_kb.load_resume(content, file.filename or "resume")

            if session:
                session["agent"].resume_kb = resume_kb
                print(f"[Resume] session={sessionId} 简历已加载, 项目={len(resume.projects)}个")

            return {
                "success": True,
                "message": "简历解析成功",
                "data": {
                    "name": resume.name,
                    "summary": resume.summary,
                    "skills": resume.skills,
                    "project_count": len(resume.projects),
                    "projects": [
                        {"name": p.name, "tech_stack": p.tech_stack, "highlights": p.highlights}
                        for p in resume.projects
                    ],
                },
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"简历解析失败: {str(e)}")

    @app.get("/api/assistant/resume/status")
    async def resume_status(sessionId: str = ""):
        """获取简历加载状态"""
        session = assistant_manager.get_session(sessionId) if sessionId else None
        resume_kb = session["resume_kb"] if session else None

        if resume_kb and resume_kb.resume:
            return {
                "loaded": True,
                "name": resume_kb.resume.name,
                "project_count": len(resume_kb.resume.projects),
                "skills": resume_kb.resume.skills,
                "search_mode": resume_kb.search_mode,
            }
        return {"loaded": False, "search_mode": "keyword"}

    @app.post("/api/assistant/resume/search-mode")
    async def set_search_mode(data: dict):
        """切换检索模式: {"mode": "keyword"} 或 {"mode": "vector", "sessionId": "xxx"}"""
        mode = data.get("mode", "keyword")
        session_id = data.get("sessionId", "")
        session = assistant_manager.get_session(session_id) if session_id else None
        resume_kb = session["resume_kb"] if session else None

        if not resume_kb:
            raise HTTPException(status_code=404, detail="未找到对应 session 的简历知识库")

        try:
            resume_kb.switch_mode(mode)
            session["agent"].resume_kb = resume_kb
            return {"success": True, "mode": resume_kb.search_mode}
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    # ============ WebSocket ============

    @app.websocket("/ws/assistant")
    async def assistant_websocket(ws: WebSocket):
        await ws.accept()

        session = assistant_manager.create_session()
        assistant_manager.active_ws[ws] = session["id"]

        # 发送会话信息
        resume_kb = session["resume_kb"]
        resume_info = {}
        if resume_kb.resume:
            resume_info = {
                "resumeLoaded": True,
                "name": resume_kb.resume.name,
                "projectCount": len(resume_kb.resume.projects),
            }
        await ws.send_json({
            "type": "config",
            "payload": {
                "sessionId": session["id"],
                "config": session["config"].model_dump(),
                "resume": resume_info,
            },
        })

        try:
            while True:
                data = await ws.receive_json()
                msg_type = data.get("type")

                if msg_type == "transcript":
                    await _handle_transcript(ws, session, data)

                elif msg_type == "config":
                    payload = data.get("payload", {})
                    for key in ["interview_type", "candidate_background", "language"]:
                        if key in payload:
                            setattr(session["config"], key, payload[key])

                    await ws.send_json({
                        "type": "config",
                        "payload": {
                            "sessionId": session["id"],
                            "config": session["config"].model_dump(),
                        },
                    })

                elif msg_type == "start_audio_capture":
                    await _handle_start_audio_capture(ws, session)

                elif msg_type == "stop_audio_capture":
                    await _handle_stop_audio_capture(session)

                elif msg_type == "list_audio_devices":
                    cap = SystemAudioCapture()
                    cap.list_devices()

                elif msg_type == "direct_question":
                    # 直接文本问题（不通过语音识别）
                    payload = data.get("payload", {})
                    question = payload.get("question", "").strip()
                    if question:
                        print(f"[Agent] 收到问题(文本): {question}")
                        await _generate_and_send_answer(ws, session, question)

        except WebSocketDisconnect:
            pass
        except Exception as e:
            print(f"[WS] 错误: {e}")
        finally:
            if session.get("audio_capture"):
                session["audio_capture"].stop()
            assistant_manager.active_ws.pop(ws, None)
            assistant_manager.remove_session(session["id"])


async def _handle_transcript(ws: WebSocket, session: dict, data: dict):
    """处理语音识别结果"""
    payload = data.get("payload", {})
    text = preprocess_transcript(payload.get("text", ""))
    is_final = payload.get("isFinal", False)

    if is_final and is_complete_question(text):
        question = extract_question(text)
        if not question or len(question) < 5:
            return

        print(f"[Agent] 收到问题: {question}")
        await _generate_and_send_answer(ws, session, question)


async def _generate_and_send_answer(ws: WebSocket, session: dict, question: str):
    """生成并流式发送 AI 回答"""
    await ws.send_json({
        "type": "status",
        "payload": {"status": "thinking", "message": "正在生成回答..."},
    })

    try:
        agent: InterviewAgent = session["agent"]
        s_cfg = session["config"]

        async for chunk in agent.generate_answer_stream(
            question=question,
            interview_type=s_cfg.interview_type,
            candidate_background=s_cfg.candidate_background,
            language=s_cfg.language,
        ):
            await ws.send_json({
                "type": "answer_chunk",
                "payload": {
                    "id": f"ans_{uuid.uuid4().hex[:8]}",
                    "chunk": chunk,
                    "isComplete": False,
                },
            })

        # 发送完成信号
        await ws.send_json({
            "type": "answer_chunk",
            "payload": {
                "id": f"ans_{uuid.uuid4().hex[:8]}",
                "chunk": "",
                "isComplete": True,
            },
        })

        print(f"[Agent] 回答完成")

    except Exception as e:
        print(f"[Agent] 生成回答失败: {e}")
        await ws.send_json({
            "type": "error",
            "payload": {"message": f"生成回答失败: {str(e)}"},
        })

    # 恢复聆听状态
    await ws.send_json({
        "type": "status",
        "payload": {"status": "listening", "message": "继续聆听..."},
    })


async def _handle_start_audio_capture(ws: WebSocket, session: dict):
    """启动系统音频捕获 + Whisper 识别"""
    cap = SystemAudioCapture()
    transcriber = WhisperTranscriber()

    last_text = ""

    async def process_loop():
        nonlocal last_text
        while cap.is_running:
            await asyncio.sleep(1.5)
            chunk = cap.get_chunk()
            if chunk is None:
                continue

            text = await transcriber.transcribe(chunk)
            if not text or text == last_text:
                continue
            last_text = text

            # 推送转写结果
            await ws.send_json({
                "type": "transcript_update",
                "payload": {"text": text, "source": "whisper"},
            })

            # 检查是否形成完整问题
            processed = preprocess_transcript(text)
            if is_complete_question(processed):
                question = extract_question(processed)
                if question and len(question) >= 5:
                    print(f"[Agent] 收到问题(音频): {question}")
                    await _generate_and_send_answer(ws, session, question)

    cap.start(lambda t, f: None)
    session["audio_capture"] = cap
    session["audio_task"] = asyncio.create_task(process_loop())

    print("[Audio] 系统音频捕获已启动")

    # ═══════════ 模拟面试 WebSocket ═══════════

    @app.websocket("/ws/mock")
    async def ws_mock_interview(websocket: WebSocket):
        """模拟面试 WebSocket"""
        print("[Mock面试] 收到 WebSocket 连接请求")
        await websocket.accept()
        session: Optional[MockInterviewSession] = None
        session_id = str(uuid.uuid4())[:8]

        try:
            while True:
                raw = await websocket.receive_text()
                data = json.loads(raw)
                msg_type = data.get("type", "")

                if msg_type == "configure":
                    payload = data.get("payload", {})
                    session = create_mock_session(
                        session_id=session_id,
                        position=payload.get("position", "全栈开发工程师"),
                        topic=payload.get("topic", "综合技术面试"),
                        difficulty=payload.get("difficulty", "medium"),
                        max_rounds=int(payload.get("max_rounds", 5)),
                    )
                    print(f"[Mock面试] 创建会话 {session_id}: {session.position} ({session.topic})")
                    await websocket.send_text(json.dumps({
                        "type": "configured", "payload": session.to_summary(),
                    }, ensure_ascii=False))

                elif msg_type == "start":
                    if not session:
                        await websocket.send_text(json.dumps({
                            "type": "error", "payload": {"message": "请先完成面试配置"}
                        }, ensure_ascii=False))
                        continue
                    question = await session.generate_question()
                    print(f"[Mock面试] 第{len(session.qa_history)}题: {question[:50]}...")
                    await websocket.send_text(json.dumps({
                        "type": "question",
                        "payload": {"question": question, "round": session.round_num, "total": session.max_rounds},
                    }, ensure_ascii=False))

                elif msg_type == "answer":
                    if not session:
                        await websocket.send_text(json.dumps({
                            "type": "error", "payload": {"message": "没有活跃的面试"}
                        }, ensure_ascii=False))
                        continue
                    answer = data.get("payload", {}).get("text", "")
                    if not answer.strip():
                        await websocket.send_text(json.dumps({
                            "type": "error", "payload": {"message": "回答不能为空"}
                        }, ensure_ascii=False))
                        continue
                    print(f"[Mock面试] 收到第{len(session.qa_history)}题回答 ({len(answer)}字)")
                    await websocket.send_text(json.dumps({
                        "type": "evaluating", "payload": {"message": "正在评估..."},
                    }, ensure_ascii=False))
                    evaluation = await session.evaluate_answer(answer)
                    print(f"[Mock面试] 评分: {evaluation.get('score', 0)}/10")
                    await websocket.send_text(json.dumps({
                        "type": "evaluation", "payload": evaluation,
                    }, ensure_ascii=False))

                elif msg_type == "next":
                    if not session:
                        await websocket.send_text(json.dumps({
                            "type": "error", "payload": {"message": "没有活跃的面试"}
                        }, ensure_ascii=False))
                        continue
                    if session.STATUS == "finished":
                        await websocket.send_text(json.dumps({
                            "type": "finished",
                            "payload": {"message": "面试已完成，请查看评估报告"},
                        }, ensure_ascii=False))
                        continue
                    question = await session.generate_question()
                    print(f"[Mock面试] 第{len(session.qa_history)}题: {question[:50]}...")
                    await websocket.send_text(json.dumps({
                        "type": "question",
                        "payload": {"question": question, "round": session.round_num, "total": session.max_rounds},
                    }, ensure_ascii=False))

                elif msg_type == "report":
                    if not session:
                        await websocket.send_text(json.dumps({
                            "type": "error", "payload": {"message": "没有活跃的面试"}
                        }, ensure_ascii=False))
                        continue
                    await websocket.send_text(json.dumps({
                        "type": "evaluating", "payload": {"message": "正在生成评估报告..."},
                    }, ensure_ascii=False))
                    report = await session.generate_report()
                    print(f"[Mock面试] 总评: {report.get('overall_score', 0)}/100")
                    try:
                        from boss.state import get_db
                        db = get_db()
                        cur = db.cursor()
                        cur.execute("""
                            INSERT INTO mock_interviews
                                (position, topic, difficulty, rounds, qa_json, score,
                                 strengths, weaknesses, overall_evaluation)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            session.position, session.topic, session.difficulty,
                            len(session.qa_history),
                            json.dumps(session.qa_history, ensure_ascii=False),
                            report.get("overall_score", 0),
                            json.dumps(report.get("strengths", []), ensure_ascii=False),
                            json.dumps(report.get("weaknesses", []), ensure_ascii=False),
                            json.dumps(report, ensure_ascii=False),
                        ))
                        db.commit()
                        cur.close()
                        print(f"[Mock面试] 报告已保存到数据库")
                    except Exception as e:
                        print(f"[Mock面试] 保存报告失败: {e}")
                    await websocket.send_text(json.dumps({
                        "type": "report", "payload": report,
                    }, ensure_ascii=False))

                elif msg_type == "skip":
                    if not session:
                        continue
                    if session.qa_history:
                        session.qa_history[-1]["a"] = "(跳过)"
                        session.qa_history[-1]["score"] = 0
                    question = await session.generate_question()
                    await websocket.send_text(json.dumps({
                        "type": "question",
                        "payload": {"question": question, "round": session.round_num, "total": session.max_rounds},
                    }, ensure_ascii=False))

                elif msg_type == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))

        except Exception as e:
            print(f"[Mock面试] WebSocket 异常: {e}")
            try:
                await websocket.close()
            except Exception:
                pass
        finally:
            if session:
                delete_mock_session(session_id)
                print(f"[Mock面试] 会话 {session_id} 已清理")


async def _handle_stop_audio_capture(session: dict):
    """停止系统音频捕获"""
    cap = session.get("audio_capture")
    if cap:
        cap.stop()
        session["audio_capture"] = None
    task = session.get("audio_task")
    if task:
        task.cancel()
        session["audio_task"] = None
    print("[Audio] 系统音频捕获已停止")
