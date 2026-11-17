"""pytest 公共夹具。

两件事：
1. 把仓库根目录和 interview/ 加进 sys.path，让 `boss.*` 和 `assistant.*` 都能导入；
2. 把 BOSS_DB_PATH 指向临时目录，每个用例跑在一张干净的表结构上 —— 绝不碰真实的
   `.boss_profile/boss_state.db`。

注意：每个用例只清空数据、不删除库文件。TestClient 在独立线程里持有自己的 SQLite
连接，Windows 上删文件会因占用失败（WinError 32）。
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
INTERVIEW_DIR = ROOT / "interview"
for _path in (str(INTERVIEW_DIR), str(ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

# 数据库隔离：必须在导入 boss.state 之前设好环境变量
_TEST_DB = Path(tempfile.mkdtemp(prefix="offer_helper_test_")) / "boss_state.db"
os.environ["BOSS_DB_PATH"] = str(_TEST_DB)

# 测试不吃开发者本机的外网 Key / 地址
for _key in ("SILICONFLOW_API_KEY", "SILICONFLOW_BASE_URL", "DEEPSEEK_API_KEY"):
    os.environ.pop(_key, None)


def _truncate_all(conn):
    tables = [
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    ]
    for table in tables:
        conn.execute(f"DELETE FROM {table}")
    try:
        conn.execute("DELETE FROM sqlite_sequence")  # 自增 id 归零，断言更好写
    except Exception:
        pass
    conn.commit()


@pytest.fixture(autouse=True)
def fresh_db():
    """每个用例：建表 → 清空数据 → 重新写入默认设置。"""
    from boss import state

    state.init_db()
    conn = state.get_db()
    _truncate_all(conn)
    state.init_db()
    yield


@pytest.fixture
def state():
    from boss import state as state_module

    return state_module
