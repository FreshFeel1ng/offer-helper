"""
面试助手 — FastAPI 服务
提供实时面试辅助（简历上传 + AI 回答流式生成 + 音频捕获）
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

app = FastAPI(title="面试助手", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "3.0.0", "module": "assistant"}


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(content="<h1>面试助手</h1><p>实时面试辅助服务运行中。请使用 WebSocket 连接 ws://host:port/ws/assistant</p>")


# 注册面试辅助模块（WebSocket + REST API）
from assistant.routes import register_assistant_routes

register_assistant_routes(app)
