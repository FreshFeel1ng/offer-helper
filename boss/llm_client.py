"""
LLM 客户端 —— 对话走设置页配置的 AI 平台，向量化走 BGE-M3。

- Embedding: 硅基流动 BGE-M3（OpenAI 兼容 /v1/embeddings，批量调用）
- 对话: 设置页配置的 AI 平台（DeepSeek / OpenRouter / 自定义），OpenAI 兼容协议
"""

import json
import os
import time
from datetime import datetime
from typing import List, Optional, Sequence

import httpx

# BGE-M3 向量化配置（硅基流动，OpenAI 兼容接口）
EMBED_DEFAULT_MODEL = "BAAI/bge-m3"
EMBED_DEFAULT_BASE = "https://api.siliconflow.cn/v1"
EMBED_BATCH_SIZE = 16
_EMBED_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


# AI配置（每次调用时从SQLite设置读取）
def _load_ai_config():
    cfg = {
        "api_key": "",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "debug_llm_context": False,
    }
    try:
        import os
        import sys

        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from boss.state import get_db, get_setting

        get_db()
        key = get_setting("ai_api_key")
        if key:
            cfg["api_key"] = key
        url = get_setting("ai_base_url")
        if url:
            cfg["base_url"] = url
        model = get_setting("ai_model")
        if model:
            cfg["model"] = model
        cfg["debug_llm_context"] = get_setting("debug_llm_context", "false") == "true"
    except Exception:
        pass
    return cfg


# 向量化配置（每次调用时从SQLite设置读取，回退环境变量）
def _load_embed_config() -> dict:
    cfg = {
        "api_key": "",
        "base_url": (os.getenv("SILICONFLOW_BASE_URL") or "").strip() or EMBED_DEFAULT_BASE,
        "model": EMBED_DEFAULT_MODEL,
    }
    try:
        from .state import get_db, get_setting

        get_db()
        key = (get_setting("siliconflow_api_key") or "").strip()
        if key:
            cfg["api_key"] = key
        model = (get_setting("embedding_model") or "").strip()
        if model:
            cfg["model"] = model
    except Exception:
        pass
    if not cfg["api_key"]:
        cfg["api_key"] = (os.getenv("SILICONFLOW_API_KEY") or "").strip()
    cfg["base_url"] = cfg["base_url"].rstrip("/")
    return cfg


def _embeddings_url(base_url: str) -> str:
    return base_url if base_url.endswith("/embeddings") else f"{base_url}/embeddings"


def get_embeddings(texts: Sequence[str], batch_size: int = EMBED_BATCH_SIZE) -> List[List[float]]:
    """批量文本向量化（BGE-M3，OpenAI 兼容 /embeddings）。

    一次请求最多 batch_size 条，避免单请求体过大；返回顺序与入参一致。
    未配置 API Key 时抛 RuntimeError —— 调用方应把向量检索当增强项，失败要降级而不是崩溃。
    """
    items = [t or "" for t in texts]
    if not items:
        return []

    cfg = _load_embed_config()
    if not cfg["api_key"]:
        raise RuntimeError(
            "未配置硅基流动 API Key（设置页「硅基流动 API Key」或环境变量 SILICONFLOW_API_KEY），无法生成 embedding"
        )

    url = _embeddings_url(cfg["base_url"])
    headers = {"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"}
    t0 = time.time()
    total_tokens = 0
    vectors: List[List[float]] = []

    with httpx.Client(timeout=_EMBED_TIMEOUT) as client:
        for start in range(0, len(items), batch_size):
            batch = items[start : start + batch_size]
            try:
                resp = client.post(
                    url,
                    json={"model": cfg["model"], "input": batch, "encoding_format": "float"},
                    headers=headers,
                )
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                body = e.response.text[:200] if e.response is not None else ""
                raise RuntimeError(f"embedding 接口返回 {e.response.status_code}: {body}") from e
            except httpx.HTTPError as e:
                raise RuntimeError(f"embedding 请求失败（{url}, model={cfg['model']}）: {e}") from e

            data = resp.json()
            total_tokens += int((data.get("usage") or {}).get("total_tokens") or 0)
            # 接口并发时不保证顺序，按 index 排序后归位
            chunk = [
                item.get("embedding") or []
                for item in sorted(data.get("data") or [], key=lambda d: d.get("index", 0))
            ]
            if len(chunk) != len(batch):
                raise RuntimeError(f"embedding 返回数量不符: 期望 {len(batch)}，实际 {len(chunk)}")
            vectors.extend(chunk)

    elapsed = time.time() - t0
    print(
        f"[{datetime.now().strftime('%H:%M:%S')}] ✅ BGE-M3 向量化完成 "
        f"(model={cfg['model']}, {len(items)} 条, {elapsed * 1000:.0f}ms)"
    )
    _log_token(cfg["model"], "embedding", 0, 0, total_tokens, elapsed)
    return vectors


def get_embedding(text: str) -> List[float]:
    """单条文本向量化（批量接口的薄封装）。"""
    vectors = get_embeddings([text])
    return vectors[0] if vectors else []


def llm_chat_deepseek(
    messages: list,
    system_prompt: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: Optional[int] = None,
) -> str:
    """调用AI API（懒加载配置，每次从SQLite读取）。"""
    t0 = time.time()
    cfg = _load_ai_config()
    if not cfg["api_key"]:
        raise RuntimeError("AI API Key未配置，请在设置页配置")

    if system_prompt:
        messages = [{"role": "system", "content": system_prompt}] + messages

    msg_count = len(messages)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔄 正在调用 AI API... (model={cfg['model']}, url={cfg['base_url']}, messages={msg_count}, temp={temperature})")
    print("─" * 60)
    for i, m in enumerate(messages):
        role = m["role"]
        content = m["content"]
        display = content if len(content) <= 3000 else content[:3000] + f"\n... [截断，原{len(content)}字符]"
        print(f"[LLM INPUT {i+1}/{msg_count}] {role}:")
        print(display)
        print()
    print("─" * 60)

    payload = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }
    if max_tokens:
        payload["max_tokens"] = max_tokens

    # 估算 payload 大小和 token 数（粗略：1 token ≈ 4 字符 for 中文, 1 token ≈ 0.75 词 for 英文）
    payload_json = json.dumps(payload, ensure_ascii=False)
    payload_kb = len(payload_json.encode("utf-8")) / 1024
    # 粗略估算输入 token（中文为主的混合文本）
    _total_chars = sum(len(m.get("content", "")) for m in messages)
    _est_tokens = int(_total_chars / 2.5)
    _api_url = f"{cfg['base_url']}/chat/completions"
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 📡 发送请求 → {_api_url}")
    print(f"[{datetime.now().strftime('%H:%M:%S')}]    Payload: {payload_kb:.1f}KB, 估算 ~{_est_tokens} input tokens, model={cfg['model']}")

    _timeout = httpx.Timeout(120.0, connect=15.0)
    _t_req = time.time()
    try:
        resp = httpx.post(
            _api_url,
            json=payload,
            headers={
                "Authorization": f"Bearer {cfg['api_key']}",
                "Content-Type": "application/json",
            },
            timeout=_timeout,
            verify=False,
        )
        _req_elapsed = time.time() - _t_req
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 📡 响应已收到 (status={resp.status_code}, 网络耗时={_req_elapsed*1000:.0f}ms)")
    except httpx.ConnectTimeout:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ 连接超时（15s内无法连接到 {_api_url}），请检查网络或 API 地址")
        raise
    except httpx.ReadTimeout:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ 读取超时（120s内未收到完整响应），服务端可能过载或 prompt 过长")
        raise
    except httpx.TimeoutException as te:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ 请求超时: {te}")
        raise
    resp.raise_for_status()
    data = resp.json()
    elapsed = time.time() - t0
    result = data["choices"][0]["message"]["content"]

    # 统计 token 用量
    usage = data.get("usage", {})
    prompt_tokens = usage.get("prompt_tokens", 0) or 0
    completion_tokens = usage.get("completion_tokens", 0) or 0
    total_tokens = usage.get("total_tokens", 0) or (prompt_tokens + completion_tokens)
    _log_token(cfg["model"], "deepseek", prompt_tokens, completion_tokens, total_tokens, elapsed)

    print(f"[LLM OUTPUT] ({len(result)} chars, {elapsed*1000:.0f}ms):")
    if total_tokens > 0:
        print(f"[LLM USAGE] prompt={prompt_tokens} completion={completion_tokens} total={total_tokens} tokens/sec={total_tokens/(elapsed if elapsed>0 else 1):.1f}")
    print(result[:2000] if len(result) > 2000 else result)
    if len(result) > 2000:
        print(f"... [截断，原{len(result)}字符]")
    print("─" * 60)
    return result


def _log_token(model: str, source: str, prompt: int, completion: int, total: int, elapsed: float):
    """记录 token 用量到数据库"""
    if total <= 0:
        return
    try:
        from .state import save_token_usage
        save_token_usage(
            model=model,
            source=source,
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=total,
            elapsed_ms=round(elapsed * 1000, 0),
        )
        print(f"[LLM TOKEN] {source}/{model}: {total}t OK")
    except Exception as e:
        print(f"[LLM TOKEN] save failed: {e}")
