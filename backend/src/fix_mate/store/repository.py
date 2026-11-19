"""仓储:所有读写数据库的方法都在这里,别处不写 SQL。

调用方负责保证同一时间只有一个修改在进行(见 services/scheduler.py 的锁),
需要多步修改同时成功或同时失败时,用 `with repo.transaction():`。
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from fix_mate.domain.models import AcceptRecord, AppNotification, Defect, ListRecord


class Repository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._in_transaction = False

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """块里的修改要么全部生效,要么全部撤销。可以嵌套,以最外层为准。"""
        if self._in_transaction:
            yield
            return
        self._conn.execute("BEGIN")
        self._in_transaction = True
        try:
            yield
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        else:
            self._conn.execute("COMMIT")
        finally:
            self._in_transaction = False

    # ---------------------------------------------------------------- 缺陷

    def all_defects(self) -> list[Defect]:
        """新的在前。"""
        rows = self._conn.execute("SELECT data FROM defects ORDER BY created_at DESC, id").fetchall()
        return [Defect.model_validate_json(r["data"]) for r in rows]

    def get_defect(self, defect_id: str) -> Defect | None:
        row = self._conn.execute("SELECT data FROM defects WHERE id = ?", (defect_id,)).fetchone()
        return Defect.model_validate_json(row["data"]) if row else None

    def save_defect(self, defect: Defect) -> None:
        self._conn.execute(
            """
            INSERT INTO defects (id, state, created_at, data) VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET state = excluded.state, data = excluded.data
            """,
            (defect.id, defect.state, defect.created_at.isoformat(), defect.model_dump_json(exclude_none=True)),
        )

    # ---------------------------------------------------------------- 清单

    def all_lists(self) -> list[ListRecord]:
        """按创建顺序。"""
        rows = self._conn.execute("SELECT data FROM lists ORDER BY position").fetchall()
        return [ListRecord.model_validate_json(r["data"]) for r in rows]

    def save_list(self, record: ListRecord) -> None:
        self._conn.execute(
            """
            INSERT INTO lists (id, position, data)
            VALUES (?, (SELECT COALESCE(MAX(position), 0) + 1 FROM lists), ?)
            ON CONFLICT(id) DO UPDATE SET data = excluded.data
            """,
            (record.id, record.model_dump_json()),
        )

    def delete_list(self, list_id: str) -> None:
        self._conn.execute("DELETE FROM lists WHERE id = ?", (list_id,))

    # ---------------------------------------------------------------- 通知

    def add_notification(self, notification: AppNotification) -> None:
        self._conn.execute(
            "INSERT INTO notifications (id, position, data) "
            "VALUES (?, (SELECT COALESCE(MAX(position), 0) + 1 FROM notifications), ?)",
            (notification.id, notification.model_dump_json(exclude_none=True)),
        )

    def notifications(self, limit: int = 50) -> list[AppNotification]:
        """新的在前。"""
        rows = self._conn.execute("SELECT data FROM notifications ORDER BY position DESC LIMIT ?", (limit,)).fetchall()
        return [AppNotification.model_validate_json(r["data"]) for r in rows]

    def mark_notifications_read(self) -> None:
        for n in self.notifications(limit=1000):
            if n.unread:
                n.unread = False
                self._conn.execute(
                    "UPDATE notifications SET data = ? WHERE id = ?", (n.model_dump_json(exclude_none=True), n.id)
                )

    # ---------------------------------------------------------------- AI 会话号

    def get_session_id(self, defect_id: str) -> str | None:
        row = self._conn.execute("SELECT session_id FROM fix_sessions WHERE defect_id = ?", (defect_id,)).fetchone()
        return row["session_id"] if row else None

    def save_session_id(self, defect_id: str, session_id: str) -> None:
        self._conn.execute(
            "INSERT INTO fix_sessions (defect_id, session_id) VALUES (?, ?) "
            "ON CONFLICT(defect_id) DO UPDATE SET session_id = excluded.session_id",
            (defect_id, session_id),
        )

    # ---------------------------------------------------------------- 接受流程的进度

    def get_accept_record(self, defect_id: str) -> AcceptRecord:
        row = self._conn.execute("SELECT data FROM accept_progress WHERE defect_id = ?", (defect_id,)).fetchone()
        return AcceptRecord.model_validate_json(row["data"]) if row else AcceptRecord()

    def save_accept_record(self, defect_id: str, record: AcceptRecord) -> None:
        self._conn.execute(
            "INSERT INTO accept_progress (defect_id, data) VALUES (?, ?) "
            "ON CONFLICT(defect_id) DO UPDATE SET data = excluded.data",
            (defect_id, record.model_dump_json()),
        )

    def delete_accept_record(self, defect_id: str) -> None:
        self._conn.execute("DELETE FROM accept_progress WHERE defect_id = ?", (defect_id,))

    def unfinished_accepts(self) -> dict[str, AcceptRecord]:
        """做了一半的接受流程:defect_id -> 进度。"""
        rows = self._conn.execute("SELECT defect_id, data FROM accept_progress").fetchall()
        return {r["defect_id"]: AcceptRecord.model_validate_json(r["data"]) for r in rows}

    # ---------------------------------------------------------------- 计数器和杂项

    def next_counter(self, name: str) -> int:
        """递增并返回一个计数器,用来生成不重复的 id。"""
        row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (name,)).fetchone()
        value = (int(row["value"]) if row else 0) + 1
        self._conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (name, str(value)),
        )
        return value

    def is_empty(self) -> bool:
        return self._conn.execute("SELECT COUNT(*) FROM defects").fetchone()[0] == 0

    def clear_all(self) -> None:
        for table in ("defects", "lists", "notifications", "meta", "fix_sessions", "accept_progress"):
            self._conn.execute(f"DELETE FROM {table}")


class RepositorySessions:
    """把 Repository 适配成引擎需要的 `SessionStore`。"""

    def __init__(self, repo: Repository):
        self._repo = repo

    def get(self, defect_id: str) -> str | None:
        return self._repo.get_session_id(defect_id)

    def save(self, defect_id: str, session_id: str) -> None:
        self._repo.save_session_id(defect_id, session_id)


class RepositoryAcceptProgress:
    """把 Repository 适配成接受流程需要的 `AcceptProgressStore`。"""

    def __init__(self, repo: Repository):
        self._repo = repo

    def get(self, defect_id: str) -> AcceptRecord:
        return self._repo.get_accept_record(defect_id)

    def save(self, defect_id: str, record: AcceptRecord) -> None:
        self._repo.save_accept_record(defect_id, record)

    def delete(self, defect_id: str) -> None:
        self._repo.delete_accept_record(defect_id)

    def unfinished(self) -> dict[str, AcceptRecord]:
        return self._repo.unfinished_accepts()
