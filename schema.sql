-- ============================================================
-- offer-helper PostgreSQL 建表语句
-- 使用方式: psql -U <user> -d <database> -f schema.sql
-- ============================================================

-- 1. 投递记录
CREATE TABLE IF NOT EXISTS applications (
    id              SERIAL PRIMARY KEY,
    job_title       VARCHAR(256)  NOT NULL DEFAULT '',
    company         VARCHAR(256)  NOT NULL DEFAULT '',
    company_id      VARCHAR(64)   NOT NULL DEFAULT '',
    salary          VARCHAR(64)   NOT NULL DEFAULT '',
    job_url         TEXT          NOT NULL DEFAULT '',
    city            VARCHAR(64)   NOT NULL DEFAULT '',
    experience      VARCHAR(32)   NOT NULL DEFAULT '',
    education       VARCHAR(32)   NOT NULL DEFAULT '',
    hr_name         VARCHAR(64)   NOT NULL DEFAULT '',
    hr_title        VARCHAR(128)  NOT NULL DEFAULT '',
    hr_active       VARCHAR(32)   NOT NULL DEFAULT '',
    description     TEXT          NOT NULL DEFAULT '',
    legal_rep       VARCHAR(64)   NOT NULL DEFAULT '',
    is_boss         SMALLINT      NOT NULL DEFAULT 0,
    area_district   VARCHAR(64)   NOT NULL DEFAULT '',
    business_district VARCHAR(128) NOT NULL DEFAULT '',
    company_size    VARCHAR(32)   NOT NULL DEFAULT '',
    industry        VARCHAR(128)  NOT NULL DEFAULT '',
    status          VARCHAR(16)   NOT NULL DEFAULT 'pending',
    greeting_text   TEXT          NOT NULL DEFAULT '',
    greeting_sent_at TIMESTAMPTZ,
    embedding       JSONB,
    optimize_result TEXT          NOT NULL DEFAULT '',
    optimize_at     TIMESTAMPTZ,
    chat_suggestion_result TEXT   NOT NULL DEFAULT '',
    chat_suggestion_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_applications_job_url UNIQUE (job_url)
);
CREATE INDEX IF NOT EXISTS idx_apps_status   ON applications (status);
CREATE INDEX IF NOT EXISTS idx_apps_company  ON applications (company);
CREATE INDEX IF NOT EXISTS idx_apps_company_id ON applications (company_id);

-- 2. HR 会话
CREATE TABLE IF NOT EXISTS conversations (
    id                  SERIAL PRIMARY KEY,
    application_id      INTEGER       REFERENCES applications(id) ON DELETE SET NULL,
    hr_name             VARCHAR(64)   NOT NULL DEFAULT '',
    hr_company          VARCHAR(256)  NOT NULL DEFAULT '',
    job_title           VARCHAR(256)  NOT NULL DEFAULT '',
    last_message_text   TEXT          NOT NULL DEFAULT '',
    last_message_from   VARCHAR(8)    NOT NULL DEFAULT 'hr',
    last_message_at     TIMESTAMPTZ,
    unread_count        INTEGER       NOT NULL DEFAULT 0,
    status              VARCHAR(16)   NOT NULL DEFAULT 'active',
    interest_level      VARCHAR(16)   NOT NULL DEFAULT '',
    hr_wechat           VARCHAR(64)   NOT NULL DEFAULT '',
    wechat_shared_at    TIMESTAMPTZ,
    resume_sent         SMALLINT      NOT NULL DEFAULT 0,
    phone_shared        SMALLINT      NOT NULL DEFAULT 0,
    transfer_requested  SMALLINT      NOT NULL DEFAULT 0,
    transfer_requested_at TIMESTAMPTZ,
    auto_reply_enabled  SMALLINT      NOT NULL DEFAULT 1,
    has_unreplied       SMALLINT      NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_conv_status     ON conversations (status);
CREATE INDEX IF NOT EXISTS idx_conv_hr_name    ON conversations (hr_name);
CREATE INDEX IF NOT EXISTS idx_conv_unreplied  ON conversations (has_unreplied, status, auto_reply_enabled);

-- 3. 聊天消息
CREATE TABLE IF NOT EXISTS messages (
    id                SERIAL PRIMARY KEY,
    conversation_id   INTEGER       NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    sender            VARCHAR(8)    NOT NULL DEFAULT 'hr',
    content           TEXT          NOT NULL DEFAULT '',
    delivery_status   VARCHAR(16)   NOT NULL DEFAULT '',
    ai_generated      SMALLINT      NOT NULL DEFAULT 0,
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages (conversation_id, created_at);

-- 4. KV 设置
CREATE TABLE IF NOT EXISTS settings (
    key         VARCHAR(64)   PRIMARY KEY,
    value       TEXT          NOT NULL DEFAULT '',
    updated_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

-- 5. 每日统计
CREATE TABLE IF NOT EXISTS daily_stats (
    date                DATE PRIMARY KEY,
    search_count        INTEGER NOT NULL DEFAULT 0,
    apply_count         INTEGER NOT NULL DEFAULT 0,
    reply_count         INTEGER NOT NULL DEFAULT 0,
    wechat_exchange_count INTEGER NOT NULL DEFAULT 0,
    interview_count     INTEGER NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 6. 候选池
CREATE TABLE IF NOT EXISTS shortlists (
    id          SERIAL PRIMARY KEY,
    job_url     TEXT          NOT NULL,
    job_title   VARCHAR(256)  NOT NULL DEFAULT '',
    company     VARCHAR(256)  NOT NULL DEFAULT '',
    salary      VARCHAR(64)   NOT NULL DEFAULT '',
    city        VARCHAR(64)   NOT NULL DEFAULT '',
    note        TEXT          NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_shortlists_job_url UNIQUE (job_url)
);

-- 7. 面试会话持久化
CREATE TABLE IF NOT EXISTS interview_sessions (
    session_id      VARCHAR(64)   PRIMARY KEY,
    job_focus       VARCHAR(256)  NOT NULL DEFAULT '',
    job_context     TEXT          NOT NULL DEFAULT '',
    resume          TEXT          NOT NULL DEFAULT '',
    round_count     INTEGER       NOT NULL DEFAULT 0,
    max_rounds      INTEGER       NOT NULL DEFAULT 10,
    history_json    JSONB         NOT NULL DEFAULT '[]',
    last_question   TEXT          NOT NULL DEFAULT '',
    last_category   VARCHAR(32)   NOT NULL DEFAULT '',
    status          VARCHAR(16)   NOT NULL DEFAULT 'active',
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

-- 8. 线下面试地点追踪
CREATE TABLE IF NOT EXISTS offline_interview_locations (
    id                SERIAL PRIMARY KEY,
    conversation_id   INTEGER       NOT NULL,
    hr_name           VARCHAR(64)   NOT NULL DEFAULT '',
    hr_company        VARCHAR(256)  NOT NULL DEFAULT '',
    job_title         VARCHAR(256)  NOT NULL DEFAULT '',
    city              VARCHAR(64)   NOT NULL DEFAULT '',
    location_detail   VARCHAR(256)  NOT NULL DEFAULT '',
    hr_message        TEXT          NOT NULL DEFAULT '',
    replied           SMALLINT      NOT NULL DEFAULT 0,
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_offline_city ON offline_interview_locations (city);

-- 9. Token 用量统计
CREATE TABLE IF NOT EXISTS token_usage (
    id                SERIAL PRIMARY KEY,
    model             VARCHAR(64)   NOT NULL DEFAULT '',
    source            VARCHAR(32)   NOT NULL DEFAULT '',
    prompt_tokens     INTEGER       NOT NULL DEFAULT 0,
    completion_tokens INTEGER       NOT NULL DEFAULT 0,
    total_tokens      INTEGER       NOT NULL DEFAULT 0,
    elapsed_ms        DOUBLE PRECISION NOT NULL DEFAULT 0,
    tokens_per_sec    DOUBLE PRECISION NOT NULL DEFAULT 0,
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

-- 10. 模拟面试记录
CREATE TABLE IF NOT EXISTS mock_interviews (
    id                  SERIAL PRIMARY KEY,
    position            VARCHAR(128) NOT NULL DEFAULT '',
    topic               VARCHAR(256) NOT NULL DEFAULT '',
    difficulty          VARCHAR(16)  NOT NULL DEFAULT 'medium',
    rounds              INTEGER      NOT NULL DEFAULT 0,
    qa_json             JSONB        NOT NULL DEFAULT '[]',
    score               INTEGER,
    strengths           TEXT,
    weaknesses          TEXT,
    overall_evaluation  TEXT,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
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
