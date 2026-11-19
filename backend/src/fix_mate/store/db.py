"""SQLite 连接和表结构。

约定:数据库连接只在事件循环所在的线程里使用,所以不会有并发访问。
本地单用户,数据量小,直接用标准库 sqlite3 加手写 SQL,一眼能看懂。

每张表只把需要查询的字段单独成列,其余整个对象存成 JSON(`data` 列)。
表结构的版本记在 `PRAGMA user_version` 里,改表结构时在 MIGRATIONS 末尾追加一条。
"""

import sqlite3
from pathlib import Path

MIGRATIONS = [
    # 版本 0 -> 1:初始表结构
    """
    CREATE TABLE defects (
        id         TEXT PRIMARY KEY,
        state      TEXT NOT NULL,
        created_at TEXT NOT NULL,
        data       TEXT NOT NULL
    );
    CREATE TABLE lists (
        id       TEXT PRIMARY KEY,
        position INTEGER NOT NULL,
        data     TEXT NOT NULL
    );
    CREATE TABLE notifications (
        id       TEXT PRIMARY KEY,
        position INTEGER NOT NULL,
        data     TEXT NOT NULL
    );
    CREATE TABLE meta (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """,
    # 版本 1 -> 2:AI 会话号。暂停后恢复时,靠它接着上次的对话继续
    """
    CREATE TABLE fix_sessions (
        defect_id  TEXT PRIMARY KEY,
        session_id TEXT NOT NULL
    );
    """,
    # 版本 2 -> 3:接受流程的进度。接受包含不可撤销的动作,做到哪一步必须落盘
    """
    CREATE TABLE accept_progress (
        defect_id TEXT PRIMARY KEY,
        data      TEXT NOT NULL
    );
    """,
]


def open_database(path: Path | str) -> sqlite3.Connection:
    """打开数据库,必要时建表或升级。path 可以是 ':memory:'(测试用)。"""
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    # isolation_level=None 是自动提交模式:每条语句立即写入磁盘。
    # (默认模式会悄悄开启事务,不手动 commit 就不落盘,进程一退出数据全丢。)
    # 需要多步一起成功或失败时,用 Repository.transaction() 显式开启事务。
    conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    for target, script in enumerate(MIGRATIONS[version:], start=version + 1):
        conn.executescript(script)
        conn.execute(f"PRAGMA user_version = {target}")
