"""转人工识别：关键词秒判 + AI 兜底 + AI 不可用时降级。"""

from boss import replier


def test_obvious_keyword_skips_llm(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("明显关键词不该调用 AI")

    monkeypatch.setattr(replier, "llm_chat_deepseek", boom)
    assert replier._needs_human_transfer("麻烦转人工，谢谢") is True


def test_plain_message_skips_llm(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("普通寒暄不该调用 AI")

    monkeypatch.setattr(replier, "llm_chat_deepseek", boom)
    assert replier._needs_human_transfer("您好，请问方便聊聊吗") is False


def test_ambiguous_message_uses_ai(monkeypatch):
    seen = {}

    def fake_chat(messages, system_prompt=None, temperature=0.3, max_tokens=None):
        seen["user_content"] = messages[-1]["content"]
        seen["max_tokens"] = max_tokens
        return "yes"

    monkeypatch.setattr(replier, "llm_chat_deepseek", fake_chat)
    assert replier._needs_human_transfer("你是AI吗") is True
    assert seen["max_tokens"] == 3  # 只要 yes/no，别让模型长篇发挥
    assert "你是AI吗" in seen["user_content"]


def test_ambiguous_message_ai_says_no(monkeypatch):
    monkeypatch.setattr(replier, "llm_chat_deepseek", lambda *a, **kw: "no")
    assert replier._needs_human_transfer("你这是自动回复吗") is False


def test_ai_failure_falls_back_to_keywords(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("AI API Key未配置")

    monkeypatch.setattr(replier, "llm_chat_deepseek", boom)
    # 模糊表达 + 不在兜底关键词里 → False；命中兜底关键词 → True
    assert replier._needs_human_transfer("你是AI吗") is False
    assert replier._needs_human_transfer("你是AI吗？不要AI") is True


def test_ambiguous_message_includes_recent_history(state, monkeypatch):
    app_id = state.add_application(
        {"title": "AI", "company": "E", "url": "https://zhipin.com/job_detail/5.html"}
    )
    conv_id = state.get_or_create_conversation(app_id, "李HR", "E", "AI")
    state.add_message(conv_id, "hr", "你好，这个岗位在招人")
    state.add_message(conv_id, "me", "您好，我在看这个岗位的机会")

    seen = {}

    def fake_chat(messages, system_prompt=None, temperature=0.3, max_tokens=None):
        seen["user_content"] = messages[-1]["content"]
        return "no"

    monkeypatch.setattr(replier, "llm_chat_deepseek", fake_chat)
    replier._needs_human_transfer("你是真人吗", conversation_id=conv_id)
    assert "最近的对话记录" in seen["user_content"]
    assert "岗位在招人" in seen["user_content"]
