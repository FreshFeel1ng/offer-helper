"""SQLite 数据层：建表、设置、投递记录、未读标记、模拟面试记录。"""

import json


def test_init_db_is_idempotent_and_seeds_defaults(state):
    state.init_db()  # 再跑一次不应该报错
    assert state.get_setting("daily_apply_limit") == "15"
    assert state.get_setting("auto_reply_enabled") == "false"
    # 不存在的 key 走默认值，不会抛异常
    assert state.get_setting("not_exists", "fallback") == "fallback"


def test_schema_has_expected_tables(state):
    conn = state.get_db()
    tables = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    assert tables == {
        "applications",
        "conversations",
        "messages",
        "settings",
        "daily_stats",
        "shortlists",
        "offline_interview_locations",
        "token_usage",
        "mock_interviews",
    }
    # 已废弃的表不该再被建出来
    assert "interview_sessions" not in tables


def test_setting_roundtrip(state):
    state.set_setting("default_city", "广州")
    assert state.get_setting("default_city") == "广州"
    assert state.get_all_settings()["default_city"] == "广州"


def test_application_by_url_is_deduped(state):
    job = {
        "title": "AI 开发工程师",
        "company": "某某科技",
        "url": "https://www.zhipin.com/job_detail/abc.html",
        "salary": "20-30K",
        "city": "广州",
    }
    first_id = state.add_application(job)
    second_id = state.add_application(job)  # 同 job_url 不应再插一条
    assert first_id == second_id

    row = state.get_application_by_url(job["url"])
    assert row["job_title"] == "AI 开发工程师"
    assert row["status"] == "pending"


def test_application_status_and_hr_active_derivation(state):
    app_id = state.add_application(
        {"title": "后端", "company": "A", "url": "https://zhipin.com/job_detail/1.html", "hr_active": "3天前活跃"}
    )
    state.update_application_status(app_id, "applied", greeting_text="您好")

    jobs = state.list_applications(status="applied")
    assert len(jobs) == 1
    assert jobs[0]["greeting_text"] == "您好"
    assert jobs[0]["hr_active_days"] == 3


def test_job_embedding_roundtrip(state):
    url = "https://zhipin.com/job_detail/2.html"
    state.add_application({"title": "算法", "company": "B", "url": url, "description": "招聘算法工程师"})
    vec = [0.1 * (i + 1) for i in range(24)]
    state.save_job_embedding(url, vec)

    rows = state.get_all_job_embeddings()
    assert len(rows) == 1
    assert rows[0]["job_url"] == url
    assert rows[0]["embedding"] == vec


def test_get_all_job_embeddings_skips_short_vectors(state):
    url = "https://zhipin.com/job_detail/3.html"
    state.add_application({"title": "测试", "company": "C", "url": url, "description": "测试岗"})
    state.save_job_embedding(url, [0.1, 0.2, 0.3])  # 维度太短，视为脏数据
    assert state.get_all_job_embeddings() == []


def _conversation_with_messages(state, messages):
    app_id = state.add_application(
        {"title": "AI", "company": "D", "url": "https://zhipin.com/job_detail/4.html"}
    )
    conv_id = state.get_or_create_conversation(app_id, "张HR", "D", "AI")
    state.replace_conversation_messages(conv_id, messages)
    return conv_id


def test_unreplied_flag_set_when_hr_spoke_last(state):
    conv_id = _conversation_with_messages(
        state, [{"sender": "me", "content": "您好"}, {"sender": "hr", "content": "在的，聊聊？"}]
    )
    assert state.get_conversation(conv_id)["has_unreplied"] == 1
    assert [c["id"] for c in state.list_unreplied_conversations()] == [conv_id]

    state.add_message(conv_id, "me", "好的")  # 我回复后自动清零
    assert state.get_conversation(conv_id)["has_unreplied"] == 0
    assert state.list_unreplied_conversations() == []


def test_unreplied_flag_ignores_system_messages(state):
    _conversation_with_messages(
        state,
        [
            {"sender": "hr", "content": "方便发份简历吗"},
            {"sender": "me", "content": "已发"},
            {"sender": "hr", "content": "BOSS安全提示：请勿线下交易"},
        ],
    )
    assert state.list_unreplied_conversations() == []


def test_mock_interview_save_and_read(state):
    mock_id = state.save_mock_interview(
        position="后端",
        topic="综合",
        difficulty="hard",
        rounds=1,
        qa_json=json.dumps([{"q": "Q1", "a": "A1", "score": 8}], ensure_ascii=False),
        score=82,
        strengths=json.dumps(["基础扎实"], ensure_ascii=False),
        weaknesses=json.dumps(["深度不足"], ensure_ascii=False),
        overall_evaluation=json.dumps({"overall_score": 82}, ensure_ascii=False),
    )
    assert mock_id

    records = state.list_mock_interviews()
    assert len(records) == 1
    assert records[0]["score"] == 82

    assert state.get_mock_interview(mock_id)["position"] == "后端"
    assert state.delete_mock_interview(mock_id) is True
    assert state.list_mock_interviews() == []


def test_token_usage_stats(state):
    state.save_token_usage(
        model="deepseek-chat", source="chat", prompt_tokens=10, completion_tokens=5, total_tokens=15, elapsed_ms=120
    )
    stats = state.get_token_stats(days=7)
    assert stats["total_tokens"] >= 15
