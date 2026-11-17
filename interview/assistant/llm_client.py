"""面试助手的 LLM 客户端 —— 直接走 OpenAI 兼容协议，无框架依赖。

只依赖 httpx：
- `chat`         同步一次性调用（简历解析、模拟面试出题/评分）
- `achat_stream` 异步流式调用（实时面试回答）
- `embed`        文本向量化（简历语义检索）

配置每次调用时从 `config` 读取，API Key 在设置页改完重启助手服务即可生效。
"""

from __future__ import annotations

import json
import re
from typing import AsyncIterator, List, Optional, Sequence

import httpx

from .config import config

_TIMEOUT = httpx.Timeout(120.0, connect=15.0)


def _ensure_api_key():
    if not (config.deepseek_api_key or "").strip():
        raise RuntimeError("AI API Key 未配置，请在设置页配置 ai_api_key")


def _chat_url() -> str:
    base = (config.deepseek_base_url or "https://api.deepseek.com/v1").rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def _embeddings_url() -> str:
    base = (config.siliconflow_base_url or "https://api.siliconflow.cn/v1").rstrip("/")
    if base.endswith("/embeddings"):
        return base
    return f"{base}/embeddings"


def _headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def estimate_tokens(text: str) -> int:
    """粗略估算 token 数（中英混合约 1.7 字符/token）。

    只用于 token 用量统计，不做上下文裁剪，误差可接受。
    """
    if not text:
        return 0
    return max(1, int(len(text) / 1.7))


def chat(
    messages: List[dict],
    temperature: float = 0.3,
    max_tokens: Optional[int] = None,
    model: Optional[str] = None,
) -> str:
    """同步调用 chat/completions，返回纯文本。"""
    _ensure_api_key()
    payload = {
        "model": model or config.llm_model,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }
    if max_tokens:
        payload["max_tokens"] = max_tokens

    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.post(_chat_url(), json=payload, headers=_headers(config.deepseek_api_key))
        resp.raise_for_status()
        data = resp.json()
    return (data["choices"][0]["message"]["content"] or "").strip()


async def achat(
    messages: List[dict],
    temperature: float = 0.3,
    max_tokens: Optional[int] = None,
    model: Optional[str] = None,
) -> str:
    """异步一次性调用。"""
    _ensure_api_key()
    payload = {
        "model": model or config.llm_model,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }
    if max_tokens:
        payload["max_tokens"] = max_tokens

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(_chat_url(), json=payload, headers=_headers(config.deepseek_api_key))
        resp.raise_for_status()
        data = resp.json()
    return (data["choices"][0]["message"]["content"] or "").strip()


async def achat_stream(
    messages: List[dict],
    temperature: float = 0.3,
    max_tokens: Optional[int] = None,
    model: Optional[str] = None,
) -> AsyncIterator[str]:
    """异步流式调用，逐段 yield 文本增量（SSE 解析，不依赖 SDK）。"""
    _ensure_api_key()
    payload = {
        "model": model or config.llm_model,
        "messages": messages,
        "temperature": temperature,
        "stream": True,
    }
    if max_tokens:
        payload["max_tokens"] = max_tokens

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        async with client.stream(
            "POST", _chat_url(), json=payload, headers=_headers(config.deepseek_api_key)
        ) as resp:
            if resp.status_code >= 400:
                body = (await resp.aread()).decode("utf-8", errors="ignore")
                raise RuntimeError(f"LLM 接口返回 {resp.status_code}: {body[:300]}")
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                chunk = line[5:].strip()
                if not chunk or chunk == "[DONE]":
                    continue
                try:
                    data = json.loads(chunk)
                except json.JSONDecodeError:
                    continue
                choices = data.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                content = delta.get("content")
                if content:
                    yield content


def parse_json_response(text: str) -> dict:
    """从 LLM 输出里抠出 JSON 对象，容忍 markdown 代码块和前后废话。"""
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`").strip()
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return {}
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


async def achat_json(
    messages: List[dict], temperature: float = 0.3, max_tokens: Optional[int] = None
) -> dict:
    """异步调用 LLM 并要求返回 JSON 对象。"""
    return parse_json_response(await achat(messages, temperature=temperature, max_tokens=max_tokens))


def _ensure_siliconflow_key():
    if not (config.siliconflow_api_key or "").strip():
        raise RuntimeError("硅基流动 API Key 未配置（siliconflow_api_key），无法做向量检索")


def embed(texts: Sequence[str], batch_size: int = 16) -> List[List[float]]:
    """文本向量化（硅基流动 BGE-M3，OpenAI 兼容 /embeddings）。"""
    _ensure_siliconflow_key()
    texts = [t or "" for t in texts]
    if not texts:
        return []

    vectors: List[List[float]] = []
    with httpx.Client(timeout=_TIMEOUT) as client:
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            payload = {"model": config.embedding_model, "input": batch}
            resp = client.post(
                _embeddings_url(), json=payload, headers=_headers(config.siliconflow_api_key)
            )
            resp.raise_for_status()
            data = resp.json()
            items = sorted(data.get("data", []), key=lambda d: d.get("index", 0))
            vectors.extend([item.get("embedding") or [] for item in items])
    return vectors
