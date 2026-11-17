"""LLM 客户端：BGE-M3 向量化 + AI 接口调用。

全部用假的 httpx 客户端，不产生任何网络请求。
"""

import httpx
import pytest

from boss import llm_client


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)
        self.request = httpx.Request("POST", "https://example.invalid")

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=self.request, response=self)


class FakeClient:
    """记录请求，按顺序返回预设响应。"""

    def __init__(self, responses, calls, *args, **kwargs):
        self._responses = list(responses)
        self._calls = calls

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def post(self, url, json=None, headers=None, **kwargs):
        self._calls.append({"url": url, "json": json, "headers": headers})
        return self._responses.pop(0)


def _patch_client(monkeypatch, responses):
    """替换 httpx.Client：embedding 走 with httpx.Client(...) 的调用路径。"""
    calls = []
    monkeypatch.setattr(
        llm_client.httpx, "Client", lambda *a, **kw: FakeClient(responses, calls, *a, **kw)
    )
    return calls


def _patch_post(monkeypatch, responses):
    """替换 httpx.post：对话接口直接用模块级 httpx.post。"""
    calls = []

    def fake_post(url, json=None, headers=None, **kwargs):
        calls.append({"url": url, "json": json, "headers": headers})
        return responses.pop(0)

    monkeypatch.setattr(llm_client.httpx, "post", fake_post)
    return calls


def _embeddings_payload(count, dim=8, offset=0):
    return {
        "data": [{"index": i, "embedding": [float(i + offset)] * dim} for i in range(count)],
        "usage": {"total_tokens": count * 3},
    }


def test_embedding_requires_api_key(state):
    state.set_setting("siliconflow_api_key", "")
    with pytest.raises(RuntimeError, match="硅基流动 API Key"):
        llm_client.get_embeddings(["你好"])


def test_embedding_uses_bge_m3_and_batches(state, monkeypatch):
    state.set_setting("siliconflow_api_key", "sk-test")
    state.set_setting("embedding_model", "BAAI/bge-m3")
    calls = _patch_client(
        monkeypatch,
        [FakeResponse(_embeddings_payload(2)), FakeResponse(_embeddings_payload(1, offset=10))],
    )

    vectors = llm_client.get_embeddings(["a", "b", "c"], batch_size=2)

    assert len(vectors) == 3
    assert [call["url"] for call in calls] == ["https://api.siliconflow.cn/v1/embeddings"] * 2
    assert calls[0]["json"]["model"] == "BAAI/bge-m3"
    assert calls[0]["json"]["input"] == ["a", "b"]
    assert calls[1]["json"]["input"] == ["c"]
    assert calls[0]["headers"]["Authorization"] == "Bearer sk-test"

    # 批量调用会记录 token 用量（设置页的成本统计依赖它）
    stats = state.get_token_stats(days=1)
    assert stats["total_tokens"] == 9


def test_embedding_env_fallback_and_empty_input(monkeypatch):
    monkeypatch.setenv("SILICONFLOW_API_KEY", "sk-env")
    monkeypatch.setenv("SILICONFLOW_BASE_URL", "http://localhost:9999/v1/")
    calls = _patch_client(monkeypatch, [FakeResponse(_embeddings_payload(1))])

    assert llm_client.get_embeddings([]) == []  # 空输入直接返回，不打接口
    assert calls == []

    llm_client.get_embedding("你好")
    assert calls[0]["url"] == "http://localhost:9999/v1/embeddings"
    assert calls[0]["headers"]["Authorization"] == "Bearer sk-env"


def test_embedding_raises_clear_error_on_http_failure(state, monkeypatch):
    state.set_setting("siliconflow_api_key", "sk-test")
    _patch_client(monkeypatch, [FakeResponse({"error": "bad model"}, status_code=400)])

    with pytest.raises(RuntimeError, match="embedding 接口返回 400"):
        llm_client.get_embeddings(["x"])


def test_embedding_raises_when_count_mismatch(state, monkeypatch):
    state.set_setting("siliconflow_api_key", "sk-test")
    _patch_client(monkeypatch, [FakeResponse(_embeddings_payload(1))])  # 发 2 条只回 1 条

    with pytest.raises(RuntimeError, match="数量不符"):
        llm_client.get_embeddings(["x", "y"])


def test_chat_passes_max_tokens(state, monkeypatch):
    state.set_setting("ai_api_key", "sk-deepseek-test")
    state.set_setting("ai_base_url", "https://api.deepseek.com")
    calls = _patch_post(
        monkeypatch,
        [
            FakeResponse(
                {"choices": [{"message": {"content": "yes"}}], "usage": {"total_tokens": 3}}
            )
        ],
    )

    answer = llm_client.llm_chat_deepseek(
        [{"role": "user", "content": "是本人吗"}], temperature=0.0, max_tokens=3
    )

    assert answer == "yes"
    assert calls[0]["json"]["max_tokens"] == 3
    assert calls[0]["url"].endswith("/chat/completions")


def test_chat_requires_api_key(state):
    state.set_setting("ai_api_key", "")
    with pytest.raises(RuntimeError, match="API Key"):
        llm_client.llm_chat_deepseek([{"role": "user", "content": "hi"}])


def test_interview_assistant_also_uses_bge_m3(monkeypatch):
    """面试模块的向量化走同一个 BGE-M3 接口（分批评分/简历检索都依赖它）。"""
    from assistant import llm_client as assistant_client
    from assistant.config import config

    monkeypatch.setattr(config, "siliconflow_api_key", "sk-interview", raising=False)
    monkeypatch.setattr(config, "embedding_model", "BAAI/bge-m3", raising=False)

    calls = []
    monkeypatch.setattr(
        assistant_client.httpx,
        "Client",
        lambda *a, **kw: FakeClient(
            [
                FakeResponse({"data": [{"index": 0, "embedding": [0.1] * 8}]}),
                FakeResponse({"data": [{"index": 0, "embedding": [0.2] * 8}]}),
            ],
            calls,
            *a,
            **kw,
        ),
    )

    vectors = assistant_client.embed(["简历块一", "简历块二"], batch_size=1)

    assert len(vectors) == 2
    assert [call["json"]["model"] for call in calls] == ["BAAI/bge-m3", "BAAI/bge-m3"]
    assert [call["json"]["input"] for call in calls] == [["简历块一"], ["简历块二"]]


def test_no_ollama_left_in_codebase():
    """回归守卫：embedding 已经全面换成 BGE-M3，不允许再把本地 Ollama 加回来。"""
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    suffixes = {".py", ".html", ".js", ".toml", ".txt", ".sh", ".example", ".yaml", ".yml"}
    offenders = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in suffixes:
            continue
        if any(part in {".git", "__pycache__", "node_modules", "data", "tests"} for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        if "ollama" in text or "11434" in text:
            offenders.append(str(path.relative_to(root)))
    assert offenders == []
