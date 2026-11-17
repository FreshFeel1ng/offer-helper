# CLAUDE.md — offer-helper

> 面向 AI 编码助手（Claude Code / DSH / Cursor 等）的项目说明：架构、目录、契约、改动禁区。
> 人类用户看 [README.md](README.md)，只想知道 CLI 怎么调看 [SKILL.md](SKILL.md)。

## 这份文档是干什么的（和 README 的区别）

三份文档分工不同，别互相抄：

| 文件 | 读者 | 回答什么问题 | 写法 |
|------|------|--------------|------|
| `README.md` | 人（第一次接触项目） | 这玩意儿能干什么、怎么装、怎么用、界面长什么样 | 产品视角，截图/徽章/功能对比表 |
| `CLAUDE.md`（本文件） | AI 编码助手 / 接手维护的人 | **代码现在长什么样**、模块边界、数据契约、为什么这么设计、哪些地方别乱动 | 工程视角，目录树/端点表/设计决策 |
| `SKILL.md` | 外部 AI Agent（运行时消费） | CLI 命令怎么调、JSON 信封什么格式、出错怎么办 | 机器契约，示例代码 |
| `offerhelper_cli/CLAUDE.md` | 改 CLI 的人 | CLI 子包的文件职责、进程管理细节 | 子模块说明 |

**更新契约（重要）**：凡是改动碰到目录结构、FastAPI 端点、WebSocket 事件、数据库表/字段、
AI 供应商（embedding / 对话模型）、Agent 工具清单、测试入口，**同一个改动里必须顺手改本文件**。
只改功能不改这里，等于把过时信息喂给下一个 AI 助手。

## 项目概述

BOSS 直聘（zhipin.com）自动化求职工具，两个进程：

- **主服务** `boss/app.py`（默认 8010）：FastAPI + WebSocket + Playwright 浏览器自动化 + AI 分析 + Agent
- **面试服务** `interview/main.py`（默认 8001）：实时面试辅助（简历 RAG + 流式回答）+ 模拟面试

核心能力：

- **搜索**：60+ 城市、福利关键词、薪资/经验/学历/规模/融资阶段多维筛选，支持多区+多规模
- **批量投递**：翻页扫描 + 公司去重 + HR 活跃度过滤 + 法人识别优先排序 + 一键批量投递
- **AI 接管聊天**：自动回复 HR（人格化）+ 自动交换微信/简历/电话 + 转人工检测 + BOSS 系统简历索取处理 + DB 未读兜底检测
- **AI 智能体**：Plan-then-Execute Agent 自主执行求职任务（一次规划→批量执行→异常重规划→总结）
- **AI 分析**：岗位匹配度分析、简历优化（24h 缓存）、沟通建议（24h 缓存）
- **面试辅助**：简历解析（MinerU / 本地兜底）→ 关键词/向量双模式检索 → 流式口语化回答
- **模拟面试**：LLM 出题 + 逐轮评分 + 标准答案 + 综合报告（WebSocket 实时推送）
- **Web 控制台**：`boss/static/` 下的浅色 SPA（HTML + Vanilla JS，无构建步骤、无 CDN）
- **CLI**：18 条命令，stdout JSON 信封，专为 AI Agent 集成设计

## 技术栈

| 层级 | 选型 |
|------|------|
| 后端 | Python ≥ 3.10 + FastAPI + Uvicorn |
| 浏览器自动化 | Playwright + Firefox 持久化 Profile + 注入 JS 反检测（`add_init_script` + `window.__bossApply`） |
| 数据库 | **只有一份 SQLite**（WAL 模式）：`.boss_profile/boss_state.db`，可用 `BOSS_DB_PATH` 覆盖；9 张表，启动时自动建表 + 补列 |
| 前端 | `dashboard.html` + `css/style.css` + `js/{app,assistant,mock,smart-send}.js`，Vanilla JS + WebSocket |
| CLI | Click + httpx + JSON 信封 |
| 对话模型 | OpenAI Chat Completions 兼容 API，设置项 `ai_api_key` / `ai_base_url` / `ai_model`（DeepSeek / OpenRouter / 小米 MiMo / 自定义） |
| 向量化（embedding） | **BGE-M3**（硅基流动 OpenAI 兼容 `/v1/embeddings`），设置项 `siliconflow_api_key` / `embedding_model`（默认 `BAAI/bge-m3`）。**不依赖任何本地模型服务** |
| 向量检索 | numpy 内存余弦相似度（无向量数据库），向量以 JSON 存 SQLite / 简历块缓存文件 |
| 包管理 | hatchling + pyproject.toml（`pip install -e .` 注册 `offerhelper` 入口） |

## 项目结构

```
boss/                          # 主服务包（FastAPI + 浏览器自动化）
├── app.py                     # 入口：REST API + WebSocket + 后台监控循环 + Agent 端点 + 面试子服务启停
├── automation.py              # 投递/聊天自动化（JS 原生点击 + Playwright 兜底、风控退避、未读兜底、回复上限）
├── firefox.py                 # BOSS 搜索 + 详情 XHR + ANTI_DETECT JS 注入 + window.__bossApply
├── replier.py                 # AI 回复生成 + 招呼语 + 转人工判定（明显关键词秒判 + AI 兜底）
├── llm_client.py              # 对话 API 调用 + BGE-M3 向量化（get_embeddings / get_embedding）
├── rag.py                     # 历史 JD RAG：矩阵化余弦相似度 + few-shot 上下文拼装
├── state.py                   # SQLite 数据层（9 张表 + 迁移 + 线程本地连接）
├── company.py                 # 公司画像聚合（岗位聚合 + HR 聚合 + 法人识别 + smart-send）
├── geo.py                     # 城市/区/规模 BOSS 编码映射（惰性获取 + 6h 缓存 + 静态回退）
├── scraper.py                 # 智联招聘独立爬虫（历史工具，不在主流程里）
├── config.yaml                # scraper.py 的数据库配置（非主流程）
├── requirements.txt           # 主服务依赖
├── agent/                     # Plan-then-Execute Agent
│   ├── prompts.py             # 规划 / 重规划 / 总结 提示模板（JSON 计划格式）
│   ├── tools.py               # 14 个原子工具 + ToolRegistry + ToolContext
│   ├── skills.py              # 3 个复合技能（smart_scan / prepare_application / smart_apply）
│   └── loop.py                # AgentLoop：规划→执行→重规划→总结（最多 10 步）
└── static/
    ├── dashboard.html         # SPA 骨架（结构 + 内联样式片段）
    ├── css/style.css          # 浅色主题样式（颜色全走 :root 令牌）
    └── js/
        ├── app.js             # 主逻辑：搜索/投递/会话/设置（含 setting ↔ 后端字段映射）
        ├── assistant.js       # 实时面试辅助面板
        ├── mock.js            # 模拟面试面板（WS /ws/mock）
        └── smart-send.js      # 智能投递面板

interview/                     # 面试服务（独立进程，默认 8001）
├── main.py                    # FastAPI 入口：/api/health + 注册 assistant 路由
├── assistant/
│   ├── config.py              # 配置（优先读 boss_state 的 settings 表，回退环境变量）
│   ├── llm_client.py          # 对话（chat/achat/achat_stream）+ BGE-M3 embed（httpx 直连，无框架）
│   ├── agent.py               # 实时面试回答 Agent（分类 → 检索简历 → 流式生成 → token 统计）
│   ├── classifier.py          # 问题分类（技术/行为/系统设计/编码/项目/职业/薪资/通用/追问 9 类）
│   ├── speech.py              # 语音转写文本清洗 + 完整问句判定 + 问句抽取
│   ├── resume.py              # 简历解析（MinerU → 本地兜底）+ 结构化 + 关键词/向量双模式检索
│   ├── mock.py                # 模拟面试会话（出题/评分/标准答案/报告，含历史薄弱点靶向出题）
│   ├── mock_routes.py         # 模拟面试 WebSocket 路由（/ws/mock）
│   ├── routes.py              # 实时面试辅助 REST + WebSocket（/ws/assistant）
│   ├── audio_capture.py       # 系统音频捕获 + Whisper 转写（可选依赖，按需导入）
│   └── README.md              # 子模块说明（端点 + 配置项）
├── data/resumes/              # 简历 JSON + `<session>/_embeddings/` 块向量缓存（个人数据，别提交）
└── requirements.txt

offerhelper_cli/               # CLI 子包（18 条命令）
├── cli.py                     # Click 命令定义
├── client.py                  # httpx 客户端（调用主服务）
├── output.py                  # JSON 信封（ok / fail / emit）
├── schema.json                # AI Agent 工具描述（供 function calling）
└── CLAUDE.md                  # CLI 子模块说明

tests/                         # pytest（离线、不联网、不启浏览器）
├── conftest.py                # BOSS_DB_PATH 指向临时库；每个用例清空数据重建
├── test_state.py              # 数据层：建表/设置/去重/未读标记/embedding 存取/模拟面试落库
├── test_api.py                # 主服务 HTTP 契约：health/status/stats/doctor/settings/agent tools/静态资源
├── test_llm_client.py         # BGE-M3 批量向量化、错误分支、max_tokens 透传、无 Ollama 回归守卫
├── test_rag.py                # 相似度排序/阈值/exclude_url/维度不兼容/上下文拼装
├── test_replier.py            # 转人工：关键词秒判、AI 兜底、AI 失败降级、上下文拼接
└── test_mock_interview.py     # 模拟面试 WebSocket 全流程（假 LLM）

根目录：README.md / CLAUDE.md / SKILL.md / CONTRIBUTING.md / pyproject.toml / schema.sql（建表参考）
      / setup.sh / .env.example / .pre-commit-config.yaml / .gitignore / .gitattributes
```

## 架构与数据流

```
浏览器 (boss/static/)
  │  WebSocket (/ws) + HTTP REST
  ▼
FastAPI (boss/app.py)  ←──HTTP───  offerhelper CLI (offerhelper_cli/)
  │
  ├── automation.py   ──Playwright/Firefox──►  zhipin.com
  │   │                ──page.evaluate()────►  window.__bossApply（注入 JS 原生操作）
  ├── replier.py      ──httpx───────────────►  对话 API（设置页配置）
  ├── rag.py          ──get_embeddings()────►  BGE-M3 /v1/embeddings
  │                   ──numpy 余弦───────────►  applications.embedding（SQLite）
  ├── state.py        ──sqlite3─────────────►  .boss_profile/boss_state.db
  ├── company.py      ──聚合查询─────────────►  内存 + DB
  ├── agent/tools.py  ──工具注册/分派────────►  automation + 对话 API
  ├── agent/skills.py ──复合技能────────────►  编排多个工具一步完成
  └── agent/loop.py   ──规划→执行→重规划────►  对话 API + 工具执行

面试服务（独立进程，8001）
  interview/main.py
    ├── assistant/routes.py    ──WS /ws/assistant──►  实时面试辅助
    ├── assistant/agent.py     ──achat_stream──────►  对话 API（流式）
    ├── assistant/resume.py    ──embed()───────────►  BGE-M3 + 块向量缓存
    └── mock_routes.py         ──WS /ws/mock───────►  模拟面试（出题/评分/报告）
```

两个服务共用同一份 SQLite（面试服务通过 `boss.state` 读写 `settings` / `mock_interviews`）。

## 数据库

SQLite（WAL），文件 `.boss_profile/boss_state.db`。`init_db()` 做三件事：建表 → 给老库补列（从建表语句反推列定义）→ 建索引 + 插默认设置，幂等。

| 表 | 用途 |
|----|------|
| `applications` | 投递记录（HR 活跃度、公司信息、法人、`optimize_result`/`chat_suggestion_result` 24h 缓存、`embedding` 历史 JD 向量） |
| `conversations` | HR 会话（微信交换、兴趣度、`has_unreplied` 未读标记、`auto_reply_enabled`） |
| `messages` | 聊天消息（`ai_generated` 标记 AI 代发） |
| `shortlists` | 候选池 |
| `daily_stats` | 每日统计 |
| `settings` | KV 配置（含 `ai_*` / `siliconflow_api_key` / `embedding_model` 等敏感信息） |
| `offline_interview_locations` | 线下面试地点登记 |
| `token_usage` | LLM/embedding token 用量（成本统计） |
| `mock_interviews` | 模拟面试记录（题目/评分/报告） |

`schema.sql` 只是建表语句的参考副本，真正的 schema 以 `boss/state.py` 的 `_SCHEMA_SQL` 为准。

## FastAPI 端点总览

主服务（`boss/app.py`，默认 8010）：

| 分类 | 端点 | 说明 |
|------|------|------|
| 页面 | `GET /`, `GET /static/*` | Web 控制台与静态资源 |
| 诊断 | `GET /api/health\|status\|stats\|doctor\|llm-stats` | 健康检查、漏斗统计、环境诊断、token 用量 |
| 系统 | `POST /api/system/start\|stop\|relogin\|heartbeat\|navigate-chat` | 浏览器生命周期 |
| 监控 | `POST /api/monitor/pause\|resume` | 自动回复控制 |
| 搜索 | `POST /api/jobs/search`, `GET /api/jobs`, `GET /api/jobs/{job_id}` | 岗位搜索与列表 |
| 投递 | `POST /api/jobs/apply\|apply-batch\|scan\|scan-and-apply`, `POST /api/jobs/{job_id}/skip` | 单投/批量/扫描 |
| AI | `POST /api/jobs/analyze\|optimize-resume\|chat-suggestion` | JD 分析/简历优化/沟通建议（后两个 24h 缓存） |
| 公司 | `GET /api/companies/preview`, `POST /api/companies/smart-send` | 公司画像/智能投递 |
| 聊天 | `GET /api/conversations[/{id}[/messages]]`, `POST /api/conversations/{id}/send\|sync\|open\|pause\|resume`, `POST /api/conversations/sync-list` | 会话管理 |
| 记录 | `GET /api/wechat-exchanges`, `GET /api/transfer-requests`, `GET /api/offline-interview-locations` | 微信交换/转人工/线下面试地点 |
| 地理 | `GET /api/geo/cities\|districts\|areas` | 城市/区/商圈 BOSS 编码 |
| 候选池 | `GET\|POST /api/shortlists`, `DELETE /api/shortlists/{sid}` | 候选池增删查 |
| 设置 | `GET\|PUT /api/settings` | KV 配置读写 |
| 模拟面试 | `GET /api/mock/list`, `GET /api/mock/{id}`, `DELETE /api/mock/{id}` | 面试记录回顾 |
| 面试子服务 | `GET /api/assistant/status`, `POST /api/assistant/start\|stop\|resume/upload` | 8001 服务进程管理 + 简历上传 |
| Agent | `GET /api/agent/tools`, `POST /api/agent/run` | Plan-then-Execute Agent |
| 调试 | `GET /api/debug/{auth,page-stats,selectors-status,legal-rep,dump-injection}`, `POST /api/debug/selector-test` | BOSS 改版时定位选择器 |
| WebSocket | `WS /ws` | 截图 + 监控/投递/Agent 事件推送 |

面试服务（`interview/main.py` + `interview/assistant/routes.py`，默认 8001）：

| 分类 | 端点 | 说明 |
|------|------|------|
| 健康 | `GET /api/health`, `GET /api/assistant/health` | 服务与活跃会话数 |
| 会话 | `POST /api/assistant/sessions` | 创建实时面试辅助会话（只保留一个活跃连接） |
| 简历 | `POST /api/assistant/resume/upload`, `GET /api/assistant/resume/status`, `POST /api/assistant/resume/search-mode` | 上传/状态/切换 `keyword`↔`vector` |
| WebSocket | `WS /ws/assistant` | 实时辅助（`transcript` / `direct_question` / `config` / `audio_capture`） |
| WebSocket | `WS /ws/mock` | 模拟面试（`configure` / `start` / `answer` / `next` / `skip` / `report` / `ping`） |

## WebSocket 事件类型

`WS /ws`（主服务）：

| 分类 | 事件类型 |
|------|----------|
| 连接 | `connected` / `pong` / `error` |
| 系统 | `system`（started/stopped/relogin_ok）、`safety_warning`、`session_expired` |
| 监控 | `monitor_paused` / `monitor_resumed` / `auto_reply_toggled` |
| 搜索投递 | `search_complete` / `apply_complete` / `batch_complete` / `scan_complete` / `scan_apply_complete` / `job_updated` |
| 聊天 | `new_messages` / `auto_reply_sent` / `manual_message_sent` / `wechat_exchanged` / `transfer_requested` |
| 设置 | `settings_updated` |
| Agent | `agent_started` / **`agent_plan`** / `agent_step` / `agent_complete` / `agent_error` |

`agent_plan` 是 Plan-then-Execute 架构特有事件：规划阶段完成后推送完整 JSON 计划（analysis / plan / constraints），前端可预览全部步骤。

`WS /ws/mock`（面试服务）：`configured` / `question` / `evaluating` / `evaluation` / `standard_answer` / `finished` / `report` / `pong` / `error`；
`WS /ws/assistant`：`config` / `status` / `answer_chunk` / `transcript_update` / `error`。

## Agent 工具清单（17 个：14 原子 + 3 复合技能）

| 工具 | 功能 |
|------|------|
| `search_jobs` | BOSS 搜索岗位 |
| `list_jobs` | 列出数据库中的岗位 |
| `get_job_detail` | 获取岗位详情 |
| `analyze_jd` | AI 分析 JD 匹配度 |
| `optimize_resume_for_jd` | AI 简历优化 |
| `get_chat_suggestion` | AI 沟通建议 |
| `apply_job` | 投递单个岗位 |
| `batch_apply` | 批量投递 |
| `list_conversations` | HR 会话列表 |
| `get_chat_messages` | 聊天消息 |
| `generate_reply` | AI 生成回复 |
| `get_status` | 系统状态 |
| `get_stats` | 投递统计 |
| `preview_companies` | 公司画像预览 |
| **⚡ `smart_scan`** | 搜索+批量 AI 分析，一步替代 search→detail×N→analyze×N |
| **⚡ `prepare_application`** | 详情+匹配+简历优化+沟通策略，一步替代 4 轮工具调用 |
| **⚡ `smart_apply`** | 分析+匹配门槛+自动投递，达标即投、不达标跳过 |

## 关键设计决策

### 向量化只走 BGE-M3，不再有本地模型
`boss/llm_client.get_embeddings()` 是唯一入口：硅基流动 `/v1/embeddings`，批量（默认 16 条/请求），
返回按 `index` 归位，token 用量写入 `token_usage`。配置优先级：设置表 `siliconflow_api_key` /
`embedding_model` → 环境变量 `SILICONFLOW_API_KEY` / `SILICONFLOW_BASE_URL` → 默认
`https://api.siliconflow.cn/v1` + `BAAI/bge-m3`。

未配 Key 时 **抛 RuntimeError 而不是崩溃**：RAG 是增强项，`rag.py` 捕获后跳过检索、主流程照常跑。
面试模块 `assistant/llm_client.embed()` 打同一个接口（同样的分批 + `index` 归位）。

**换 embedding 模型会让历史向量失效**：`similar_jds` 会跳过维度不一致的历史向量（打印条数），
重新点一次「简历优化」即可覆盖该岗位的向量。

### 历史 JD RAG 检索（boss/rag.py）
相似度阈值 0.55，取 top-5（调用方各取 3）。实现上把所有历史向量拼成一个矩阵，归一化后**一次矩阵乘法**
算出全部相似度，再按阈值过滤排序 —— 历史记录变多时不退化成 Python 循环逐条算。

`ensure_jd_embedding()` 与 `similar_jds(query_vec=...)` 配合：同一段 JD 在「入库」和「检索」之间共用
一份向量，一次请求只调一次 embedding 接口。支持三种上下文模式：`optimize`（引用历史优化建议）、
`greeting`（引用历史招呼语 + HR 反馈信号）、`chat`（引用历史沟通建议）。

### 风控绕开（双层策略）
**第一层 — 数据采集（XHR 代理）**：`page.evaluate(fetch)` 在浏览器内发请求，自动带 cookie/referer。
**第二层 — 投递操作（注入 JS 原生操作）**：`add_init_script` 注入 `window.__bossApply(greeting)`，
JS 内用原生 DOM API 完成「找按钮 → `dispatchEvent(MouseEvent)` → 等聊天弹窗 → `textContent` + `InputEvent`
逐字输入 → 发送」，避免 Playwright `locator.click()` 被 CDP runtime 检测。
普通页面导航和 DOM 抓取仍用 Playwright，只有高风险点击/输入切到注入 JS。

### 公司去重 / HR 活跃度 / 风控退避
- 去重：`_normalize_company_name` 模糊匹配中缀后缀变体（"字节跳动" vs "字节跳动科技"）。
- HR 活跃度：搜索时抓最近活跃时间，超过阈值自动跳过；法人（Boss 身份）优先排序。
- 退避：`_trigger_cooldown` 指数退避，基础冷却 rate_limit=120s / captcha=600s / banned=3600s，
  连续触发翻倍上限 7200s；成功或冷却结束清零 `_risk_strikes`；冷却期心跳保活照常、仅跳过高风险操作。

### AI 缓存
简历优化与沟通建议两个端点带 24h 持久化缓存（`optimize_result` / `chat_suggestion_result` 存 SQLite），
同 JD 不重复烧 token；`force_refresh` 可绕过。

### CLI JSON 信封
所有命令 stdout 只输出 `{ok, command, data, pagination?, error}`，stderr 输出日志，exit 0=成功 1=失败。

### Plan-then-Execute Agent 循环
1. **规划**（1 次 LLM）：生成 JSON 计划（工具名 + 参数 + 原因 + 约束）
2. **执行**（0 次 LLM）：按序调用工具，支持 `$N` 引用前步结果
3. **重规划**（仅异常，最多 2 次）
4. **总结**（0-1 次 LLM）

计划步数上限 10，优先用复合技能；执行器遵守用户约束（如"不投递"则跳过 `apply_job`）。

### 监控循环与 Agent 互斥
`chat_monitor_loop` 与 `/api/agent/run` 共享 `asyncio.Lock`（`browser_sync_lock`），同一事件循环内互斥。
单轮最多回复 3 条（`_MAX_REPLIES_THIS_CYCLE`）：先同步全部消息，再回复前 3 条。

### 未读消息双重检测（DOM + DB 兜底）
`conversations.has_unreplied` 在 `replace_conversation_messages()` 时计算（最后一条非系统 HR 消息之后
没有 "me" 回复则置 1），`add_message(sender="me")` 置 0。DOM 扫描漏掉的会话由
`list_unreplied_conversations()` 兜底（排除本轮已处理的 `_processed_conv_ids`）。

### BOSS 系统简历索取处理
检测到「同意 + 是否同意/附件简历」时，用注入 JS 在聊天消息区点「同意」（排除弹窗内按钮）；
找不到才回退到工具栏 `send_resume()`。

### 人类行为模拟
`_human_pace(min,max)` 随机间隔放在 AI 生成**之后**（避免叠加过长延迟）；`_human_scroll()` 投递前
随机滚动 1-3 次 + 停留 0.8-2.5s，滚完 `scrollTo(0,0)` 防止 Playwright auto-scroll 触发 header 动画。

### 面试辅助的检索链路
问题进来 → `speech.py` 清洗/判完整问句 → `classifier.py` 规则分类（9 类）→ `resume.py` 取上下文
（`keyword` 关键词打分 或 `vector` BGE-M3 块向量 + 块缓存 `_embeddings/*.json`，失败自动回退关键词）
→ `agent.py` 拼 messages → `achat_stream` 流式 SSE 解析 → 逐段推送 `answer_chunk`。

### 模拟面试
`mock.py` 每次出题把历史 Q&A + 历史薄弱点（`list_mock_interviews` 里的 weaknesses）注入 prompt 靶向提升；
评分与标准答案分两次 LLM 调用，先推 `evaluation` 再推 `standard_answer`，报告落 `mock_interviews` 表。

## 测试

```bash
python -m pytest -q            # 全量：离线、不联网、不启浏览器
python -m pytest tests/test_rag.py -v
```

约定（改测试前先读 `tests/conftest.py`）：

- `BOSS_DB_PATH` 在 conftest 导入时指向临时目录，**任何用例都不允许碰真实的 `.boss_profile/boss_state.db`**；
  `fresh_db` 自动夹具每个用例清空数据并重新写入默认设置（只清数据、不删库文件 —— TestClient 在自己的
  线程里持有 SQLite 连接，Windows 上删文件会 WinError 32）。
- 所有 LLM / embedding 调用必须 monkeypatch（`boss.llm_client.httpx.*`、`assistant.llm_client.achat`），
  测试里出现真实网络请求就是 bug。
- `test_llm_client.py::test_no_ollama_left_in_codebase` 是回归守卫：扫描全仓库，禁止再引入本地 Ollama 依赖。

## 常用命令

```bash
# 安装
pip install -e .
playwright install firefox

# 主服务
python -m boss.app --port 8010        # 或 python boss/app.py --port 8010
# 面试服务
cd interview && python -m uvicorn main:app --port 8001

# CLI 核心流程
offerhelper doctor                          # 环境诊断
offerhelper search "AI Agent" --city 广州    # 搜索岗位
offerhelper scan-apply --max-pages 5         # 翻 5 页扫描投递
offerhelper apply-batch                      # 批量投递待投递
offerhelper stats                            # 投递漏斗
offerhelper schema                           # 输出工具描述 JSON

# 测试 / Lint
python -m pytest -q
python -m ruff check boss interview tests
```

## 配置

| 项目 | 位置 |
|------|------|
| 对话模型 | 设置页（存 `settings` 表）：`ai_api_key` / `ai_base_url` / `ai_model` |
| 向量化 | 设置页：`siliconflow_api_key` / `embedding_model`（默认 `BAAI/bge-m3`） |
| 简历解析 | 设置页：`mineru_api_token`（可选，失败回退 PyMuPDF） |
| 浏览器 | `boss/config.yaml`（headless / profile_dir，`firefox.py` 使用） |
| 投递参数 | 设置页：招呼语模板/模式、每日上限、回复间隔、HR 不活跃阈值、公司去重 |
| CLI 后端地址 | 环境变量 `OFFERHELPER_API`（默认 `http://127.0.0.1:8010`） |
| 数据库位置 | 环境变量 `BOSS_DB_PATH`（默认 `.boss_profile/boss_state.db`） |
| 运行时数据 | `.boss_profile/`（SQLite + Firefox Profile，gitignored）、`interview/data/resumes/`（简历与块向量，个人数据别提交） |

## 已知问题 / 维护备注

最近一轮清理（2026-11）已经修掉：`offerhelper server --start` / `restart` 的启动路径、进程匹配、
`on_event` → `lifespan`、`humanizer.py`（已删除）、`interview_sessions` 表与 5 个读写函数（已删除）。

仍然存在、动手时注意：

- `boss/agent/*` 里还有少量未使用的导入（ruff F401），不影响运行，改到那个文件时顺手清。
- `boss/scraper.py`（智联招聘）与 `boss/config.yaml` 是历史工具，不在主流程里，别把它当主应用配置改。
- `offerhelper` 的 `server`/`restart` 用 `sys.executable -m boss.app` 启动；如果你改包名或移动 `boss/app.py`，
  记得同步 `offerhelper_cli/cli.py` 的 `_project_dir()` 与 `_BOSS_CMDLINE_MARKERS`。

## 合规边界

- 仅用于个人账号求职辅助
- 每日投递有上限（默认 15 条）
- 风控触发时自动冷却退避
- 不得批量注册、商业采集、规避风控
