# 面试辅助模块 (Assistant)

从 InterviewAssistant-python 集成到 offer-helper 的实时面试辅助模块。

## 功能概述

- **实时面试回答生成**: 监听面试官提问 → 问题分类 → RAG检索简历 → AI流式生成回答
- **简历解析与RAG**: 支持 PDF/DOCX/TXT 解析，LLM提取结构化信息，关键词/向量双模式检索
- **语音识别**: 支持前端语音识别结果处理 或 服务端系统音频捕获+Whisper
- **回答人性化**: 书面语→口语转换，添加自然填充词

## 模块结构

```
assistant/
├── __init__.py       # 包初始化
├── config.py         # 配置管理（兼容 boss_state SQLite）
├── agent.py          # 核心 AI Agent（LangChain + LLM 流式生成）
├── classifier.py     # 面试问题分类器（9种类型）
├── speech.py         # 语音文本预处理与问题检测
├── humanizer.py      # 回答人性化后处理
├── resume.py         # 简历解析 + RAG知识库
├── audio_capture.py  # 系统音频捕获 + Whisper转录
├── vector_rag.py     # BGE-M3 + Milvus 向量检索
├── routes.py         # FastAPI 路由 + WebSocket 端点
└── README.md         # 本文件
```

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

向量检索需要 Milvus (localhost:19530) 和硅基流动 BGE-M3 API。
