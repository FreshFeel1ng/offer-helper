"""历史 JD RAG 检索：相似度排序、阈值、维度兼容、上下文拼装。"""

import json

import pytest

from boss import rag

DIM = 24
QUERY_VEC = [1.0] + [0.0] * (DIM - 1)


def _vec(first: float, second: float = 0.0) -> list:
    return [first, second] + [0.0] * (DIM - 2)


def _add_job(state, url, title, embedding, **extra):
    state.add_application(
        {
            "title": title,
            "company": extra.pop("company", "某某科技"),
            "url": url,
            "description": extra.pop("description", "招聘 AI 工程师，熟悉 Python、RAG 检索与向量数据库。"),
        }
    )
    if embedding is not None:
        state.save_job_embedding(url, embedding)
    return url


@pytest.fixture
def history(state):
    _add_job(state, "https://zhipin.com/job_detail/a.html", "AI 工程师", _vec(1.0))
    _add_job(state, "https://zhipin.com/job_detail/b.html", "前端工程师", _vec(0.0, 1.0))
    _add_job(state, "https://zhipin.com/job_detail/c.html", "数据工程师", [0.5] * 12)  # 旧模型维度
    return state


def test_similar_jds_ranks_and_filters(history, monkeypatch):
    monkeypatch.setattr(rag, "get_embedding", lambda text: QUERY_VEC)

    results = rag.similar_jds("招聘 AI 工程师，要求熟悉 Python 和 RAG 检索", limit=5)

    assert [item["job_title"] for item in results] == ["AI 工程师"]
    assert results[0]["similarity"] == pytest.approx(1.0, abs=1e-6)
    assert "embedding" not in results[0]  # 向量不外传


def test_similar_jds_respects_exclude_url(history, monkeypatch):
    monkeypatch.setattr(rag, "get_embedding", lambda text: QUERY_VEC)

    results = rag.similar_jds(
        "招聘 AI 工程师，要求熟悉 Python 和 RAG 检索",
        exclude_url="https://zhipin.com/job_detail/a.html",
    )
    assert results == []


def test_similar_jds_short_text_skips_embedding(history, monkeypatch):
    def boom(text):
        raise AssertionError("文本太短不该调用 embedding")

    monkeypatch.setattr(rag, "get_embedding", boom)
    assert rag.similar_jds("太短") == []


def test_similar_jds_reuses_supplied_vector(history, monkeypatch):
    """调用方已经算过向量时不能再打一次 embedding 接口。"""

    def boom(text):
        raise AssertionError("不该重复调用 embedding")

    monkeypatch.setattr(rag, "get_embedding", boom)
    results = rag.similar_jds("招聘 AI 工程师，要求熟悉 Python 和 RAG 检索", query_vec=QUERY_VEC)
    assert [item["job_title"] for item in results] == ["AI 工程师"]


def test_similar_jds_survives_embedding_failure(history, monkeypatch):
    def boom(text):
        raise RuntimeError("未配置硅基流动 API Key")

    monkeypatch.setattr(rag, "get_embedding", boom)
    assert rag.similar_jds("招聘 AI 工程师，要求熟悉 Python 和 RAG 检索") == []


def test_ensure_jd_embedding_caches_to_db(history, monkeypatch):
    url = "https://zhipin.com/job_detail/a.html"
    monkeypatch.setattr(rag, "get_embedding", lambda text: QUERY_VEC)  # 已有向量，不该被调用
    assert rag.ensure_jd_embedding(url, "招聘 AI 工程师，要求熟悉 Python 和 RAG 检索") == QUERY_VEC

    new_url = _add_job(history, "https://zhipin.com/job_detail/d.html", "算法工程师", None)
    calls = []

    def fake_embed(text):
        calls.append(text)
        return QUERY_VEC

    monkeypatch.setattr(rag, "get_embedding", fake_embed)
    desc = "招聘算法工程师，需要推荐系统与排序模型经验，熟悉 Python"
    assert rag.ensure_jd_embedding(new_url, desc) == QUERY_VEC
    assert len(calls) == 1
    # 第二次直接从库里读，不再调接口
    assert rag.ensure_jd_embedding(new_url, desc) == QUERY_VEC
    assert len(calls) == 1


def test_build_rag_context_modes(history, monkeypatch):
    monkeypatch.setattr(rag, "get_embedding", lambda text: QUERY_VEC)
    similar = rag.similar_jds("招聘 AI 工程师，要求熟悉 Python 和 RAG 检索")
    similar[0]["optimize_result"] = "把项目经历改成 STAR 结构，动作 + 产物 + 结果，补上量化数字"
    similar[0]["chat_suggestion_result"] = "先问团队规模和当前业务重点，再谈技术栈匹配度"
    similar[0]["greeting_text"] = "您好，我做过 RAG 检索优化，命中率提升明显"
    similar[0]["interest_level"] = "high"

    assert rag.build_rag_context([], "optimize") == ""

    optimize_ctx = rag.build_rag_context(similar, "optimize")
    assert "AI 工程师" in optimize_ctx
    assert "STAR 结构" in optimize_ctx

    chat_ctx = rag.build_rag_context(similar, "chat")
    assert "团队规模" in chat_ctx

    greeting_ctx = rag.build_rag_context(similar, "greeting")
    assert "RAG 检索优化" in greeting_ctx
    assert "HR 兴趣度" in greeting_ctx


def test_state_exposes_full_job_embeddings(history):
    rows = history.get_all_job_embeddings()
    assert len(rows) == 2  # 12 维的脏数据被跳过
    assert {row["job_title"] for row in rows} == {"AI 工程师", "前端工程师"}
    assert json.loads(json.dumps(rows[0]["embedding"])) == rows[0]["embedding"]
