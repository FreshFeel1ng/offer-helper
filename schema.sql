-- ============================================================
-- offer-helper SQLite 建表语句（参考用）
-- 说明：程序启动时 boss/state.py 会自动建表 + 补列，无需手动执行。
-- 如需手工建库：sqlite3 .boss_profile/boss_state.db < schema.sql
-- ============================================================

-- 1. 投递记录
CREATE TABLE IF NOT EXISTS applications (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    job_title               TEXT    NOT NULL DEFAULT '',
    company                 TEXT    NOT NULL DEFAULT '',
    company_id              TEXT    NOT NULL DEFAULT '',
    salary                  TEXT    NOT NULL DEFAULT '',
    job_url                 TEXT    NOT NULL DEFAULT '',
    city                    TEXT    NOT NULL DEFAULT '',
    experience              TEXT    NOT NULL DEFAULT '',
    education               TEXT    NOT NULL DEFAULT '',
    hr_name                 TEXT    NOT NULL DEFAULT '',
    hr_title                TEXT    NOT NULL DEFAULT '',
    hr_active               TEXT    NOT NULL DEFAULT '',
    description             TEXT    NOT NULL DEFAULT '',
    legal_rep               TEXT    NOT NULL DEFAULT '',
    is_boss                 INTEGER NOT NULL DEFAULT 0,
    area_district           TEXT    NOT NULL DEFAULT '',
    business_district       TEXT    NOT NULL DEFAULT '',
    company_size            TEXT    NOT NULL DEFAULT '',
    industry                TEXT    NOT NULL DEFAULT '',
    status                  TEXT    NOT NULL DEFAULT 'pending',
    greeting_text           TEXT    NOT NULL DEFAULT '',
    greeting_sent_at        TEXT,
    embedding               TEXT,
    optimize_result         TEXT    NOT NULL DEFAULT '',
    optimize_at             TEXT,
    chat_suggestion_result  TEXT    NOT NULL DEFAULT '',
    chat_suggestion_at      TEXT,
    created_at              TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at              TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_applications_job_url
    ON applications (job_url) WHERE job_url != '';
CREATE INDEX IF NOT EXISTS idx_apps_status     ON applications (status);
CREATE INDEX IF NOT EXISTS idx_apps_company    ON applications (company);
CREATE INDEX IF NOT EXISTS idx_apps_company_id ON applications (company_id);

-- 2. HR 会话
CREATE TABLE IF NOT EXISTS conversations (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id          INTEGER REFERENCES applications(id) ON DELETE SET NULL,
    hr_name                 TEXT    NOT NULL DEFAULT '',
    hr_company              TEXT    NOT NULL DEFAULT '',
    job_title               TEXT    NOT NULL DEFAULT '',
    last_message_text       TEXT    NOT NULL DEFAULT '',
    last_message_from       TEXT    NOT NULL DEFAULT 'hr',
    last_message_at         TEXT,
    unread_count            INTEGER NOT NULL DEFAULT 0,
    status                  TEXT    NOT NULL DEFAULT 'active',
    interest_level          TEXT    NOT NULL DEFAULT '',
    hr_wechat               TEXT    NOT NULL DEFAULT '',
    wechat_shared_at        TEXT,
    resume_sent             INTEGER NOT NULL DEFAULT 0,
    phone_shared            INTEGER NOT NULL DEFAULT 0,
    transfer_requested      INTEGER NOT NULL DEFAULT 0,
    transfer_requested_at   TEXT,
    auto_reply_enabled      INTEGER NOT NULL DEFAULT 1,
    has_unreplied           INTEGER NOT NULL DEFAULT 0,
    created_at              TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at              TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_conv_status    ON conversations (status);
CREATE INDEX IF NOT EXISTS idx_conv_hr_name   ON conversations (hr_name);
CREATE INDEX IF NOT EXISTS idx_conv_unreplied ON conversations (has_unreplied, status, auto_reply_enabled);

-- 3. 聊天消息
CREATE TABLE IF NOT EXISTS messages (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id   INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    sender            TEXT    NOT NULL DEFAULT 'hr',
    content           TEXT    NOT NULL DEFAULT '',
    delivery_status   TEXT    NOT NULL DEFAULT '',
    ai_generated      INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages (conversation_id, created_at);

-- 4. KV 设置
CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL DEFAULT '',
    updated_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 5. 每日统计
CREATE TABLE IF NOT EXISTS daily_stats (
    date                  TEXT PRIMARY KEY,
    search_count          INTEGER NOT NULL DEFAULT 0,
    apply_count           INTEGER NOT NULL DEFAULT 0,
    reply_count           INTEGER NOT NULL DEFAULT 0,
    wechat_exchange_count INTEGER NOT NULL DEFAULT 0,
    interview_count       INTEGER NOT NULL DEFAULT 0,
    created_at            TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 6. 候选池
CREATE TABLE IF NOT EXISTS shortlists (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_url     TEXT NOT NULL,
    job_title   TEXT NOT NULL DEFAULT '',
    company     TEXT NOT NULL DEFAULT '',
    salary      TEXT NOT NULL DEFAULT '',
    city        TEXT NOT NULL DEFAULT '',
    note        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_shortlists_job_url ON shortlists (job_url);

-- 7. 线下面试地点追踪
CREATE TABLE IF NOT EXISTS offline_interview_locations (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id   INTEGER NOT NULL,
    hr_name           TEXT NOT NULL DEFAULT '',
    hr_company        TEXT NOT NULL DEFAULT '',
    job_title         TEXT NOT NULL DEFAULT '',
    city              TEXT NOT NULL DEFAULT '',
    location_detail   TEXT NOT NULL DEFAULT '',
    hr_message        TEXT NOT NULL DEFAULT '',
    replied           INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_offline_city ON offline_interview_locations (city);

-- 8. Token 用量统计
CREATE TABLE IF NOT EXISTS token_usage (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    model             TEXT NOT NULL DEFAULT '',
    source            TEXT NOT NULL DEFAULT '',
    prompt_tokens     INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens      INTEGER NOT NULL DEFAULT 0,
    elapsed_ms        REAL NOT NULL DEFAULT 0,
    tokens_per_sec    REAL NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 9. 模拟面试记录
CREATE TABLE IF NOT EXISTS mock_interviews (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    position            TEXT NOT NULL DEFAULT '',
    topic               TEXT NOT NULL DEFAULT '',
    difficulty          TEXT NOT NULL DEFAULT 'medium',
    rounds              INTEGER NOT NULL DEFAULT 0,
    qa_json             TEXT NOT NULL DEFAULT '[]',
    score               INTEGER,
    strengths           TEXT,
    weaknesses          TEXT,
    overall_evaluation  TEXT,
    created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 初始默认设置
INSERT INTO settings (key, value) VALUES
    ('greeting_template', '您好！看到贵司在招{job_title}，很感兴趣。PS：正在和你聊天的这个AI工具是我自己开发的——就当是我的技术名片了'),
    ('greeting_enabled', 'true'),
    ('ai_greeting_enabled', 'true'),
    ('ai_reply_style', 'professional'),
    ('daily_apply_limit', '15'),
    ('auto_reply_enabled', 'false'),
    ('min_reply_delay_sec', '20'),
    ('max_reply_delay_sec', '40'),
    ('batch_delay_min_sec', '45'),
    ('batch_delay_max_sec', '120'),
    ('batch_rest_every', '8'),
    ('resume_summary', ''),
    ('wechat_id', ''),
    ('search_keywords', ''),
    ('default_city', '深圳')
ON CONFLICT (key) DO NOTHING;
