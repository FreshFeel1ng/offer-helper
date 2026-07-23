#!/usr/bin/env python3
"""
PostgreSQL 数据层 —— 投递记录、聊天消息、设置、每日统计。
"""

import os
import re
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

import psycopg2
import psycopg2.extras
import psycopg2.errors

# 尝试加载 .env 文件（项目根目录）
try:
    from dotenv import load_dotenv
    for _env_path in [
        Path(__file__).parent.parent / ".env",      # boss/state.py → 项目根目录
        Path(__file__).parent / ".env",              # boss/state.py 同目录
    ]:
        if _env_path.exists():
            load_dotenv(_env_path)
            break
except ImportError:
    pass


def _get_db_config() -> dict:
    """从环境变量读取 PostgreSQL 连接配置"""
    return {
        "host": os.getenv("PG_HOST", "localhost"),
        "port": int(os.getenv("PG_PORT", "5432")),
        "user": os.getenv("PG_USER", "root"),
        "password": os.getenv("PG_PASSWORD", ""),
        "dbname": os.getenv("PG_DATABASE", "postgres"),
    }

_local = threading.local()


def get_db() -> psycopg2.extensions.connection:
    """获取当前线程的 PostgreSQL 连接（自动使用 RealDictCursor，兼容原 sqlite3.Row 的字典访问）"""
    if not hasattr(_local, "conn") or _local.conn is None or _local.conn.closed:
        cfg = _get_db_config()
        _local.conn = psycopg2.connect(**cfg, cursor_factory=psycopg2.extras.RealDictCursor)
        _local.conn.autocommit = False
    return _local.conn


def init_db():
    """初始化数据库：插入默认设置（表已由用户手动创建）"""
    db = get_db()
    cur = db.cursor()

    defaults = {
        "greeting_template": "您好！看到贵司在招{job_title}，很感兴趣。PS：正在和你聊天的这个AI工具是我自己开发的——就当是我的技术名片了",
        "greeting_enabled": "true",
        "ai_greeting_enabled": "true",
        "ai_reply_style": "professional",
        "daily_apply_limit": "15",
        "auto_reply_enabled": "false",
        "min_reply_delay_sec": "20",
        "max_reply_delay_sec": "40",
        "batch_delay_min_sec": "45",
        "batch_delay_max_sec": "120",
        "batch_rest_every": "8",
        "resume_summary": "",
        "wechat_id": "",
        "search_keywords": "",
        "default_city": "淄博",
    }
    for k, v in defaults.items():
        cur.execute(
            "INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING",
            (k, v),
        )
    db.commit()
    cur.close()


def _row_to_dict(row) -> Optional[dict]:
    return dict(row) if row else None


def _rows_to_list(rows) -> List[dict]:
    return [dict(r) for r in rows]


def _apply_hr_active_days(job: dict):
    """将 hr_active 字符串转为 hr_active_days / hr_active_label。"""
    raw = (job.get("hr_active") or "").strip()
    if not raw:
        return
    job["hr_active_label"] = raw
    m = re.search(r"(\d+)", raw)
    if m:
        job["hr_active_days"] = int(m.group(1))
        return
    if "今日" in raw or "刚刚" in raw or "在线" in raw:
        job["hr_active_days"] = 0
    elif "昨日" in raw or "昨天" in raw:
        job["hr_active_days"] = 1
    elif "本周" in raw:
        job["hr_active_days"] = 3
    elif "本月" in raw or "近月" in raw:
        job["hr_active_days"] = 7
    elif "半年前" in raw or "超过半年" in raw:
        job["hr_active_days"] = 180
    else:
        job["hr_active_days"] = 14


# ══════════════════════════════════════
#  Applications
# ══════════════════════════════════════


def add_application(job: dict) -> int:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """INSERT INTO applications
           (job_title, company, company_id, salary, job_url, city, experience, education, hr_name, hr_title, hr_active, description, legal_rep, is_boss, area_district, business_district, company_size, industry)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (job_url) DO NOTHING
           RETURNING id""",
        (
            job.get("title", ""),
            job.get("company", ""),
            job.get("company_id", ""),
            job.get("salary", ""),
            job.get("url", ""),
            job.get("city", ""),
            job.get("experience", ""),
            job.get("education", ""),
            job.get("hr_name", ""),
            job.get("hr_title", ""),
            job.get("hr_active", ""),
            job.get("description", ""),
            job.get("legal_rep", ""),
            1 if job.get("is_boss") else 0,
            job.get("area_district", ""),
            job.get("business_district", ""),
            job.get("company_size", ""),
            job.get("industry", ""),
        ),
    )
    row = cur.fetchone()
    db.commit()
    cur.close()
    return row["id"] if row else 0


def get_application(app_id: int) -> Optional[dict]:
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM applications WHERE id=%s", (app_id,))
    row = cur.fetchone()
    cur.close()
    return _row_to_dict(row)


def get_application_by_url(url: str) -> Optional[dict]:
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM applications WHERE job_url=%s", (url,))
    row = cur.fetchone()
    cur.close()
    return _row_to_dict(row)


def update_application_from_job(app_id: int, job: dict) -> Optional[dict]:
    """用本次搜索结果刷新已有岗位；空值不覆盖旧值。"""
    fields = {
        "job_title": job.get("title", ""),
        "company": job.get("company", ""),
        "company_id": job.get("company_id", ""),
        "salary": job.get("salary", ""),
        "city": job.get("city", ""),
        "experience": job.get("experience", ""),
        "education": job.get("education", ""),
        "hr_name": job.get("hr_name", ""),
        "hr_title": job.get("hr_title", ""),
        "hr_active": job.get("hr_active", ""),
        "description": job.get("description", ""),
        "area_district": job.get("area_district", ""),
        "business_district": job.get("business_district", ""),
        "company_size": job.get("company_size", ""),
        "industry": job.get("industry", ""),
    }
    params = []
    assignments = []
    for column, value in fields.items():
        value = (value or "").strip()
        assignments.append(f"{column}=CASE WHEN %s!='' THEN %s ELSE {column} END")
        params.extend([value, value])
    params.append(app_id)

    db = get_db()
    cur = db.cursor()
    cur.execute(
        f"""UPDATE applications SET {", ".join(assignments)},
            updated_at=CURRENT_TIMESTAMP WHERE id=%s""",
        params,
    )
    db.commit()
    cur.close()
    return get_application(app_id)


def list_applications(status: Optional[str] = None, limit: int = 50) -> List[dict]:
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if status:
        cur.execute(
            "SELECT * FROM applications WHERE status=%s ORDER BY updated_at DESC LIMIT %s",
            (status, limit),
        )
    else:
        cur.execute("SELECT * FROM applications ORDER BY updated_at DESC LIMIT %s", (limit,))
    rows = cur.fetchall()
    cur.close()
    result = _rows_to_list(rows)
    for j in result:
        _apply_hr_active_days(j)
    return result


def update_application_status(app_id: int, status: str, greeting_text: Optional[str] = None):
    db = get_db()
    cur = db.cursor()
    if greeting_text:
        cur.execute(
            """UPDATE applications SET status=%s, greeting_text=%s, greeting_sent_at=CURRENT_TIMESTAMP,
               updated_at=CURRENT_TIMESTAMP WHERE id=%s""",
            (status, greeting_text, app_id),
        )
    else:
        cur.execute(
            "UPDATE applications SET status=%s, updated_at=CURRENT_TIMESTAMP WHERE id=%s",
            (status, app_id),
        )
    db.commit()
    cur.close()


def get_today_application_count() -> int:
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT COUNT(*) as cnt FROM applications WHERE greeting_sent_at::date = CURRENT_DATE")
    row = cur.fetchone()
    cur.close()
    return row["cnt"] if row else 0


def get_today_pending_count() -> int:
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT COUNT(*) as cnt FROM applications WHERE status='pending'")
    row = cur.fetchone()
    cur.close()
    return row["cnt"] if row else 0


def count_hours_replied_in_range(hours: int) -> int:
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT COUNT(*) as cnt FROM conversations WHERE last_message_from='hr' AND last_message_at > NOW() - INTERVAL '1 hour' * %s",
        (hours,),
    )
    row = cur.fetchone()
    cur.close()
    return row["cnt"] if row else 0


def count_interest_level(level: str) -> int:
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT COUNT(*) as cnt FROM conversations WHERE interest_level=%s", (level,))
    row = cur.fetchone()
    cur.close()
    return row["cnt"] if row else 0


def get_pending_applications(limit: int = 50) -> List[dict]:
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT * FROM applications WHERE status='pending' AND job_url!='' ORDER BY id LIMIT %s",
        (limit,),
    )
    rows = cur.fetchall()
    cur.close()
    return _rows_to_list(rows)


def list_jobs_by_company(company_id: str = "", company: str = "") -> List[dict]:
    """按 company_id 或 company 名返回该公司下所有已入库的岗位。"""
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if company_id:
        cur.execute(
            "SELECT * FROM applications WHERE company_id=%s ORDER BY id DESC",
            (company_id,),
        )
        rows = cur.fetchall()
        if rows:
            cur.close()
            return _rows_to_list(rows)
    if company:
        cur.execute(
            "SELECT * FROM applications WHERE company=%s ORDER BY id DESC",
            (company,),
        )
        rows = cur.fetchall()
        cur.close()
        return _rows_to_list(rows)
    cur.close()
    return []


def list_companies_by_position_count(min_count: int = 1, limit: int = 50) -> List[dict]:
    """按公司聚合，统计 distinct job_url 数倒序。"""
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """SELECT company, company_id, COUNT(DISTINCT job_url) AS position_count, MAX(id) AS latest_job_id
           FROM applications
           WHERE company != '' AND job_url != ''
           GROUP BY company, COALESCE(NULLIF(company_id, ''), company)
           HAVING COUNT(DISTINCT job_url) >= %s
           ORDER BY position_count DESC, latest_job_id DESC
           LIMIT %s""",
        (min_count, limit),
    )
    rows = cur.fetchall()
    cur.close()
    return _rows_to_list(rows)


def company_already_applied(company: str = "", company_id: str = "") -> bool:
    """该公司下是否已经有 status in (applied, replied) 的记录。"""
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if company_id:
        cur.execute(
            "SELECT 1 FROM applications WHERE company_id=%s AND status IN ('applied','replied') LIMIT 1",
            (company_id,),
        )
        row = cur.fetchone()
        if row:
            cur.close()
            return True
    if company:
        cur.execute(
            "SELECT 1 FROM applications WHERE company=%s AND status IN ('applied','replied') LIMIT 1",
            (company,),
        )
        row = cur.fetchone()
        cur.close()
        return bool(row)
    cur.close()
    return False


def save_job_embedding(job_url: str, embedding: list):
    """存储 JD 的 embedding 向量（JSON 格式）。"""
    import json
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE applications SET embedding=%s WHERE job_url=%s",
        (json.dumps(embedding, ensure_ascii=False), job_url),
    )
    db.commit()
    cur.close()


def get_all_job_embeddings() -> list:
    """返回所有已存储 embedding 的岗位摘要 + HR 反馈信号。"""
    import json
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """SELECT a.job_url, a.job_title, a.company, a.description, a.embedding,
                  a.optimize_result, a.chat_suggestion_result, a.greeting_text, a.status,
                  c.interest_level, c.resume_sent, c.hr_wechat, c.wechat_shared_at
           FROM applications a
           LEFT JOIN conversations c ON c.application_id = a.id
           WHERE a.embedding IS NOT NULL AND a.embedding != ''
           ORDER BY a.id DESC""",
    )
    rows = cur.fetchall()
    cur.close()
    result = []
    for r in rows:
        emb_str = r["embedding"]
        if not emb_str:
            continue
        try:
            emb = json.loads(emb_str)
        except Exception:
            continue
        if not emb or len(emb) < 16:
            continue
        result.append({
            "job_url": r["job_url"],
            "job_title": r["job_title"],
            "company": r["company"],
            "description": (r["description"] or "")[:500],
            "embedding": emb,
            "optimize_result": r["optimize_result"] or "",
            "chat_suggestion_result": r["chat_suggestion_result"] or "",
            "greeting_text": r["greeting_text"] or "",
            "status": r["status"] or "",
            "interest_level": r["interest_level"] or "",
            "resume_sent": bool(r["resume_sent"]),
            "wechat_shared": bool(r["hr_wechat"] and r["wechat_shared_at"]),
        })
    return result


# ══════════════════════════════════════
#  Conversations
# ══════════════════════════════════════


def get_or_create_conversation(application_id: int, hr_name: str, hr_company: str, job_title: str) -> int:
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if application_id:
        cur.execute("SELECT id FROM conversations WHERE application_id=%s", (application_id,))
        row = cur.fetchone()
        if row:
            cur.close()
            return row["id"]
    name = hr_name.strip() if hr_name else ""
    if name:
        cur.execute("SELECT id FROM conversations WHERE hr_name=%s AND status!='closed'", (name,))
        row = cur.fetchone()
        if row:
            cur.close()
            return row["id"]
    cur.close()

    cur = db.cursor()
    cur.execute(
        """INSERT INTO conversations (application_id, hr_name, hr_company, job_title)
           VALUES (%s, %s, %s, %s)
           RETURNING id""",
        (application_id, name, hr_company, job_title),
    )
    row = cur.fetchone()
    db.commit()
    cur.close()
    return row["id"]


def get_conversation(conv_id: int) -> Optional[dict]:
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM conversations WHERE id=%s", (conv_id,))
    row = cur.fetchone()
    cur.close()
    return _row_to_dict(row)


def list_active_conversations() -> List[dict]:
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM conversations WHERE status!='closed' ORDER BY updated_at DESC")
    rows = cur.fetchall()
    cur.close()
    return _rows_to_list(rows)


def list_unreplied_conversations() -> List[dict]:
    """返回 has_unreplied=1 且 status=active 且 auto_reply_enabled=1 的会话"""
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT * FROM conversations WHERE has_unreplied=1 AND status='active' AND auto_reply_enabled=1 ORDER BY updated_at DESC"
    )
    rows = cur.fetchall()
    cur.close()
    return _rows_to_list(rows)


def find_conversation_by_hr_name(hr_name: str) -> Optional[dict]:
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT * FROM conversations WHERE hr_name=%s ORDER BY updated_at DESC LIMIT 1",
        (hr_name,),
    )
    row = cur.fetchone()
    cur.close()
    return _row_to_dict(row)


def update_conversation_last_message(conv_id: int, text: str, sender: str, unread_delta: int = 0):
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """UPDATE conversations SET last_message_text=%s, last_message_from=%s,
           last_message_at=CURRENT_TIMESTAMP, unread_count=GREATEST(0, unread_count+%s),
           updated_at=CURRENT_TIMESTAMP WHERE id=%s""",
        (text[:200], sender, unread_delta, conv_id),
    )
    db.commit()
    cur.close()


def update_conversation_status(conv_id: int, status: str):
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE conversations SET status=%s, updated_at=CURRENT_TIMESTAMP WHERE id=%s",
        (status, conv_id),
    )
    db.commit()
    cur.close()


def update_conversation_interest(conv_id: int, level: str):
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE conversations SET interest_level=%s, updated_at=CURRENT_TIMESTAMP WHERE id=%s",
        (level, conv_id),
    )
    db.commit()
    cur.close()


def update_conversation_wechat(conv_id: int, wechat_id: str):
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE conversations SET hr_wechat=%s, wechat_shared_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP WHERE id=%s",
        (wechat_id, conv_id),
    )
    db.commit()
    cur.close()


def mark_resume_sent(conv_id: int):
    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE conversations SET resume_sent=1, updated_at=CURRENT_TIMESTAMP WHERE id=%s", (conv_id,))
    db.commit()
    cur.close()


def mark_phone_shared(conv_id: int):
    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE conversations SET phone_shared=1, updated_at=CURRENT_TIMESTAMP WHERE id=%s", (conv_id,))
    db.commit()
    cur.close()


def get_wechat_exchanges() -> List[dict]:
    """返回所有已获取到微信号的会话，包含岗位详情。"""
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """SELECT c.id, c.hr_name, c.hr_company, c.job_title, c.hr_wechat,
                  c.wechat_shared_at, c.interest_level,
                  a.city, a.salary, a.experience, a.education, a.description
           FROM conversations c
           LEFT JOIN applications a ON c.application_id = a.id
           WHERE c.hr_wechat IS NOT NULL AND c.hr_wechat != ''
           ORDER BY c.wechat_shared_at DESC"""
    )
    rows = cur.fetchall()
    cur.close()
    return _rows_to_list(rows)


def update_conversation_transfer_requested(conv_id: int):
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE conversations SET transfer_requested=1, transfer_requested_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP WHERE id=%s",
        (conv_id,),
    )
    db.commit()
    cur.close()


def get_transfer_requests() -> List[dict]:
    """返回所有转人工请求的会话，包含岗位详情。"""
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """SELECT c.id, c.hr_name, c.hr_company, c.job_title, c.last_message_text,
                  c.transfer_requested_at, c.interest_level,
                  a.city, a.salary, a.experience, a.education, a.description
           FROM conversations c
           LEFT JOIN applications a ON c.application_id = a.id
           WHERE c.transfer_requested = 1
           ORDER BY c.transfer_requested_at DESC"""
    )
    rows = cur.fetchall()
    cur.close()
    return _rows_to_list(rows)


def set_auto_reply(conv_id: int, enabled: bool):
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE conversations SET auto_reply_enabled=%s, updated_at=CURRENT_TIMESTAMP WHERE id=%s",
        (1 if enabled else 0, conv_id),
    )
    db.commit()
    cur.close()


# ══════════════════════════════════════
#  Messages
# ══════════════════════════════════════


def add_message(
    conversation_id: int, sender: str, content: str, ai_generated: bool = False, delivery_status: str = ""
) -> int:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "INSERT INTO messages (conversation_id, sender, content, delivery_status, ai_generated) VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (conversation_id, sender, content, delivery_status, 1 if ai_generated else 0),
    )
    row = cur.fetchone()
    # 我发消息后标记为已回复
    if sender == "me":
        cur.execute(
            "UPDATE conversations SET has_unreplied=0, updated_at=CURRENT_TIMESTAMP WHERE id=%s",
            (conversation_id,),
        )
    db.commit()
    cur.close()
    return row["id"]


def get_messages(conversation_id: int, limit: int = 50) -> List[dict]:
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT * FROM messages WHERE conversation_id=%s ORDER BY created_at ASC, id ASC LIMIT %s",
        (conversation_id, limit),
    )
    rows = cur.fetchall()
    cur.close()
    return _rows_to_list(rows)


def get_recent_messages(conversation_id: int, limit: int = 5) -> List[dict]:
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT * FROM messages WHERE conversation_id=%s ORDER BY created_at DESC, id DESC LIMIT %s",
        (conversation_id, limit),
    )
    rows = cur.fetchall()
    cur.close()
    return _rows_to_list(rows)


def replace_conversation_messages(conversation_id: int, messages: List[dict]):
    """用 BOSS 当前消息历史覆盖本地缓存，避免 Web 端展示过期或错会话内容。"""
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT content FROM messages WHERE conversation_id=%s AND ai_generated=1",
        (conversation_id,),
    )
    old_ai = {r["content"] for r in cur.fetchall()}
    cur.close()

    cur = db.cursor()
    cur.execute("DELETE FROM messages WHERE conversation_id=%s", (conversation_id,))
    for msg in messages:
        sender = msg.get("sender", "hr")
        content = (msg.get("content") or "").strip()
        delivery_status = (msg.get("status") or msg.get("delivery_status") or "").strip()
        if not content:
            continue
        ai_generated = 1 if sender == "me" and content in old_ai else 0
        cur.execute(
            "INSERT INTO messages (conversation_id, sender, content, delivery_status, ai_generated) VALUES (%s, %s, %s, %s, %s)",
            (conversation_id, sender, content, delivery_status, ai_generated),
        )
    # 自动判断: 最后一条非系统HR消息之后是否有"me"的回复
    _system_prefixes = (
        "你与该职位竞争者PK情况", "竞争力分析", "BOSS安全提示",
        "系统消息", "沟通分析", "今日推荐", "该Boss已查看了你的简历",
        "对方已查看了您的附件简历",
    )
    _has_unreplied = 0
    for i in range(len(messages) - 1, -1, -1):
        m = messages[i]
        if m.get("sender") != "hr":
            continue
        if (m.get("content") or "").startswith(_system_prefixes):
            continue
        _has_reply = any(
            messages[j].get("sender") == "me"
            for j in range(i + 1, len(messages))
        )
        _has_unreplied = 0 if _has_reply else 1
        break
    cur.execute(
        "UPDATE conversations SET has_unreplied=%s, updated_at=CURRENT_TIMESTAMP WHERE id=%s",
        (_has_unreplied, conversation_id),
    )
    db.commit()
    cur.close()


def get_last_hr_message(conversation_id: int) -> Optional[dict]:
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT * FROM messages WHERE conversation_id=%s AND sender='hr' ORDER BY created_at DESC LIMIT 1",
        (conversation_id,),
    )
    row = cur.fetchone()
    cur.close()
    return _row_to_dict(row)


def message_exists(conversation_id: int, content: str, sender: str) -> bool:
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT id FROM messages WHERE conversation_id=%s AND content=%s AND sender=%s ORDER BY created_at DESC LIMIT 1",
        (conversation_id, content, sender),
    )
    row = cur.fetchone()
    cur.close()
    return row is not None


# ══════════════════════════════════════
#  Settings
# ══════════════════════════════════════


def get_setting(key: str, default: str = "") -> str:
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT value FROM settings WHERE key=%s", (key,))
    row = cur.fetchone()
    cur.close()
    return row["value"] if row else default


def set_setting(key: str, value: str):
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "INSERT INTO settings (key, value, updated_at) VALUES (%s, %s, CURRENT_TIMESTAMP) ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=CURRENT_TIMESTAMP",
        (key, value),
    )
    db.commit()
    cur.close()


def get_all_settings() -> dict:
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT key, value FROM settings")
    rows = cur.fetchall()
    cur.close()
    return {r["key"]: r["value"] for r in rows}


# ══════════════════════════════════════
#  Daily Stats
# ══════════════════════════════════════


def _today() -> str:
    return date.today().isoformat()


def _ensure_today():
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "INSERT INTO daily_stats (date) VALUES (%s) ON CONFLICT (date) DO NOTHING",
        (_today(),),
    )
    db.commit()
    cur.close()


def increment_daily_stat(field: str):
    _ensure_today()
    db = get_db()
    cur = db.cursor()
    cur.execute(
        f"UPDATE daily_stats SET {field} = {field} + 1 WHERE date=%s",
        (_today(),),
    )
    db.commit()
    cur.close()


def get_daily_stats(date_str: Optional[str] = None) -> dict:
    d = date_str or _today()
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM daily_stats WHERE date=%s", (d,))
    row = cur.fetchone()
    cur.close()
    return dict(row) if row else {}


def get_today_auto_reply_count() -> int:
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT COUNT(*) as cnt FROM messages WHERE ai_generated=1 AND created_at::date = CURRENT_DATE"
    )
    row = cur.fetchone()
    cur.close()
    return row["cnt"] if row else 0


# ═══════════════════════
#  候选池
# ═══════════════════════


def add_to_shortlist(
    job_url: str, title: str, company: str = "", salary: str = "", city: str = "", note: str = ""
) -> int:
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute(
            "INSERT INTO shortlists (job_url, job_title, company, salary, city, note) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
            (job_url, title, company, salary, city, note),
        )
        row = cur.fetchone()
        db.commit()
        cur.close()
        return row["id"]
    except psycopg2.errors.UniqueViolation:
        db.rollback()
        cur.close()
        return 0


def remove_from_shortlist(shortlist_id: int):
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM shortlists WHERE id=%s", (shortlist_id,))
    db.commit()
    cur.close()


def list_shortlists(limit: int = 100) -> list:
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM shortlists ORDER BY created_at DESC LIMIT %s", (limit,))
    rows = cur.fetchall()
    cur.close()
    return _rows_to_list(rows)


def is_in_shortlist(job_url: str) -> bool:
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT COUNT(*) as cnt FROM shortlists WHERE job_url=%s", (job_url,))
    row = cur.fetchone()
    cur.close()
    return row["cnt"] > 0 if row else False


# ══════════════════════════════════════
#  面试会话持久化
# ══════════════════════════════════════


def save_interview_session(
    session_id: str,
    job_focus: str = "",
    job_context: str = "",
    resume: str = "",
    round_count: int = 0,
    max_rounds: int = 10,
    history_json: str = "[]",
    last_question: str = "",
    last_category: str = "",
    status: str = "active",
):
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """INSERT INTO interview_sessions
           (session_id, job_focus, job_context, resume, round_count, max_rounds,
            history_json, last_question, last_category, status, updated_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
           ON CONFLICT (session_id) DO UPDATE SET
               job_focus=EXCLUDED.job_focus,
               job_context=EXCLUDED.job_context,
               resume=EXCLUDED.resume,
               round_count=EXCLUDED.round_count,
               max_rounds=EXCLUDED.max_rounds,
               history_json=EXCLUDED.history_json,
               last_question=EXCLUDED.last_question,
               last_category=EXCLUDED.last_category,
               status=EXCLUDED.status,
               updated_at=CURRENT_TIMESTAMP""",
        (session_id, job_focus, job_context, resume, round_count, max_rounds,
         history_json, last_question, last_category, status),
    )
    db.commit()
    cur.close()


def get_interview_session(session_id: str) -> dict | None:
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT * FROM interview_sessions WHERE session_id=%s", (session_id,)
    )
    row = cur.fetchone()
    cur.close()
    return dict(row) if row else None


def list_active_interview_sessions() -> list:
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT session_id, job_focus, round_count, status, created_at, updated_at "
        "FROM interview_sessions WHERE status='active' ORDER BY updated_at DESC"
    )
    rows = cur.fetchall()
    cur.close()
    return _rows_to_list(rows)


def list_all_interview_sessions() -> list:
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT session_id, job_focus, round_count, status, created_at, updated_at "
        "FROM interview_sessions ORDER BY updated_at DESC"
    )
    rows = cur.fetchall()
    cur.close()
    return _rows_to_list(rows)


def mark_interview_ended(session_id: str):
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE interview_sessions SET status='ended', updated_at=CURRENT_TIMESTAMP WHERE session_id=%s",
        (session_id,),
    )
    db.commit()
    cur.close()


# ══════════════════════════════════════
#  线下面试地点追踪
# ══════════════════════════════════════

_KNOWN_CITIES = [
    "上海", "北京", "深圳", "广州", "杭州", "成都", "武汉", "南京", "西安",
    "重庆", "苏州", "天津", "长沙", "郑州", "东莞", "青岛", "合肥", "佛山",
    "宁波", "昆明", "沈阳", "大连", "福州", "厦门", "济南", "无锡", "南宁",
    "长春", "泉州", "贵阳", "南昌", "常州", "太原", "烟台", "嘉兴", "南通",
    "金华", "珠海", "惠州", "徐州", "海口", "乌鲁木齐", "兰州", "中山",
    "绍兴", "温州", "潍坊", "哈尔滨", "淄博", "临沂", "台州", "湖州",
    "芜湖", "镇江", "扬州", "盐城", "泰州", "襄阳", "宜昌", "洛阳",
]

_OFFLINE_INTERVIEW_KEYWORDS = [
    "线下面试", "线下", "现场面试", "到面", "到场面试", "实地面试", "面对面",
    "过来面试", "来面试", "到公司面试", "面聊", "见面聊聊", "面谈",
    "线下面聊", "线下沟通", "实地面聊", "到场", "到公司聊", "当面聊聊",
    "当面面试", "线下一面", "线下二面", "线下面", "实地", "线下笔试",
    "来公司", "到司面试", "上门面试", "线下复试", "线下面试地点",
    "面试地点", "面试地址", "线下面试地址", "线下详聊", "到现场", "公司地址",
]


def _extract_city_from_text(text: str) -> tuple:
    """从文本中提取城市和地点详情。返回 (city, location_detail)。"""
    if not text:
        return ("", "")
    found_cities = []
    for city in _KNOWN_CITIES:
        if city in text:
            found_cities.append(city)
    if not found_cities:
        return ("", "")
    city = found_cities[-1]
    detail = ""
    detail_patterns = [
        r'(?:在|到|去|地址[：:]?\s*)([一-龥]{2,20}(?:区|路|街|道|镇|园|大厦|广场|中心|楼|层|号))',
        r'([一-龥]{2,10}(?:区|街道|镇|园区|开发区))',
        r'(?:地点|地址|位置)[：:]\s*([^\n，。,]{2,50})',
    ]
    for pat in detail_patterns:
        m = re.search(pat, text)
        if m:
            detail = m.group(1).strip()
            break
    if not detail and len(found_cities) >= 2:
        detail = found_cities[0]
    return (city, detail)


def _detect_offline_interview_requirement(message: str) -> bool:
    """检测HR消息是否要求线下面试。"""
    if not message:
        return False
    return any(kw in message for kw in _OFFLINE_INTERVIEW_KEYWORDS)


def save_offline_interview_location(
    conversation_id: int,
    hr_name: str = "",
    hr_company: str = "",
    job_title: str = "",
    city: str = "",
    location_detail: str = "",
    hr_message: str = "",
) -> int:
    """保存线下面试地点记录。已存在则更新。返回记录ID。"""
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT id FROM offline_interview_locations WHERE conversation_id=%s",
        (conversation_id,),
    )
    row = cur.fetchone()
    cur.close()

    cur = db.cursor()
    if row:
        cur.execute(
            """UPDATE offline_interview_locations
               SET hr_name=%s, hr_company=%s, job_title=%s, city=%s,
                   location_detail=%s, hr_message=%s, updated_at=CURRENT_TIMESTAMP
               WHERE id=%s
               RETURNING id""",
            (hr_name, hr_company, job_title, city, location_detail, hr_message, row["id"]),
        )
        result_row = cur.fetchone()
        db.commit()
        cur.close()
        return result_row["id"]
    cur.execute(
        """INSERT INTO offline_interview_locations
           (conversation_id, hr_name, hr_company, job_title, city, location_detail, hr_message)
           VALUES (%s, %s, %s, %s, %s, %s, %s)
           RETURNING id""",
        (conversation_id, hr_name, hr_company, job_title, city, location_detail, hr_message),
    )
    result_row = cur.fetchone()
    db.commit()
    cur.close()
    return result_row["id"]


def list_offline_interview_locations() -> list:
    """获取所有线下面试地点，按城市分组排序。"""
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """SELECT * FROM offline_interview_locations
           ORDER BY city, updated_at DESC"""
    )
    rows = cur.fetchall()
    cur.close()
    return _rows_to_list(rows)


def get_offline_locations_grouped() -> dict:
    """获取按城市分组的线下面试地点。"""
    locations = list_offline_interview_locations()
    grouped = {}
    for loc in locations:
        city = loc.get("city", "") or "未分类"
        if city not in grouped:
            grouped[city] = []
        grouped[city].append(loc)
    return dict(sorted(grouped.items(), key=lambda x: len(x[1]), reverse=True))


def mark_offline_location_replied(location_id: int):
    """标记线下面试地点记录已回复。"""
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE offline_interview_locations SET replied=1, updated_at=CURRENT_TIMESTAMP WHERE id=%s",
        (location_id,),
    )
    db.commit()
    cur.close()


# ══════════════════════════════════════
#  Token 用量统计
# ══════════════════════════════════════


def save_token_usage(
    model: str = "",
    source: str = "",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    elapsed_ms: float = 0,
):
    db = get_db()
    cur = db.cursor()
    tps = total_tokens / (elapsed_ms / 1000) if elapsed_ms > 0 else 0
    cur.execute(
        """INSERT INTO token_usage (model, source, prompt_tokens, completion_tokens, total_tokens, elapsed_ms, tokens_per_sec)
           VALUES (%s,%s,%s,%s,%s,%s,%s)""",
        (model, source, prompt_tokens, completion_tokens, total_tokens, elapsed_ms, round(tps, 1)),
    )
    db.commit()
    cur.close()


def get_token_stats(days: int = 7) -> dict:
    """获取最近 N 天的 Token 统计"""
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """SELECT
             COUNT(*) as total_calls,
             COALESCE(SUM(total_tokens),0) as total_tokens,
             COALESCE(SUM(prompt_tokens),0) as total_prompt_tokens,
             COALESCE(SUM(completion_tokens),0) as total_completion_tokens,
             COALESCE(ROUND(AVG(tokens_per_sec),1),0) as avg_tps,
             COALESCE(ROUND(AVG(elapsed_ms),0),0) as avg_elapsed_ms
           FROM token_usage
           WHERE created_at >= CURRENT_DATE - INTERVAL '1 day' * %s""",
        (days,),
    )
    row = cur.fetchone()
    cur.close()
    return dict(row) if row else {}


def list_token_usage(limit: int = 20) -> list:
    """最近 N 条用量记录"""
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT * FROM token_usage ORDER BY created_at DESC LIMIT %s",
        (limit,),
    )
    rows = cur.fetchall()
    cur.close()
    return _rows_to_list(rows)


# 启动时初始化
init_db()
