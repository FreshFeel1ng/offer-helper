# 面试辅助模块 (Assistant)

从 InterviewAssistant-python 集成到 offer-helper 的实时面试辅助模块。

## 功能概述

- **实时面试回答生成**: 监听面试官提问 → 问题分类 → 检索简历 → AI流式生成回答
- **简历解析与检索**: 支持 PDF/DOCX/TXT 解析，LLM提取结构化信息，关键词/向量双模式检索
- **语音识别**: 支持前端语音识别结果处理 或 服务端系统音频捕获+Whisper（可选）
- **模拟面试**: 自动出题 + 逐轮评分 + 标准答案 + 综合报告

## 模块结构

```
assistant/
├── __init__.py       # 包初始化
├── config.py         # 配置管理（兼容 boss_state SQLite）
├── llm_client.py     # LLM 客户端（OpenAI 兼容协议，httpx 直连）
├── agent.py          # 核心 AI Agent（流式回答生成）
├── classifier.py     # 面试问题分类器（9种类型）
├── speech.py         # 语音文本预处理与问题检测
├── resume.py         # 简历解析 + 知识库（关键词 / 内存向量检索）
├── audio_capture.py  # 系统音频捕获 + Whisper转录（可选依赖）
├── mock.py           # 模拟面试会话逻辑
├── mock_routes.py    # 模拟面试 WebSocket 路由
├── routes.py         # FastAPI 路由 + WebSocket 端点
└── README.md         # 本文件
```

技术选型：**不依赖 LangChain / Milvus 等框架**，LLM 与 embedding 直接走 OpenAI 兼容 HTTP 接口，
向量检索用 numpy 在内存里做余弦相似度（块向量缓存在 `data/resumes/<session>/_embeddings/`），
因此部署只需要 Python + 该服务所需依赖，不需要 Docker / 向量数据库。

## API 端点

### REST API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/assistant/health` | 健康检查 |
| POST | `/api/assistant/sessions` | 创建面试辅助会话 |
| POST | `/api/assistant/resume/upload` | 上传简历文件 |
| GET | `/api/assistant/resume/status` | 查询简历状态 |
| POST | `/api/assistant/resume/search-mode` | 切换检索模式 |

### WebSocket

| 端点 | 说明 |
|------|------|
| `/ws/assistant` | 实时面试辅助 WebSocket |

**客户端→服务端消息:**

| type | 说明 |
|------|------|
| `transcript` | 语音识别结果 |
| `direct_question` | 直接文本问题 |
| `config` | 更新会话配置 |
| `start_audio_capture` | 启动音频捕获 |
| `stop_audio_capture` | 停止音频捕获 |
| `list_audio_devices` | 列出音频设备 |

**服务端→客户端消息:**

| type | 说明 |
|------|------|
| `config` | 会话配置 |
| `status` | 状态更新 |
| `answer_chunk` | 流式AI回答 |
| `transcript_update` | 音频转文字结果 |
| `error` | 错误信息 |

## 配置

LLM 配置自动从 offer-helper 的 `boss_state` SQLite settings 表读取，回退到环境变量。

| 配置项 | 用途 |
|--------|------|
| `ai_api_key` / `ai_base_url` / `ai_model` | 回答生成、简历信息提取、模拟面试出题与评分 |
| `siliconflow_api_key` / `embedding_model` | 向量检索（BGE-M3，仅在"向量"模式下需要） |
| `mineru_api_token` | PDF 精准解析（可选，失败自动回退本地解析） |

## 运行

```bash
pip install -r interview/requirements.txt
cd interview && python -m uvicorn main:app --port 8001
```

系统音频捕获另需 `pip install sounddevice openai`（可选，不装只能文字问答）。
