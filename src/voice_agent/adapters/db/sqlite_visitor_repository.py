from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from voice_agent.domain.call_session import CallSession


class SQLiteVisitorRepository:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._connection = sqlite3.connect(str(database_path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._ensure_schema()

    def create_session(self, call_sid: str | None = None) -> CallSession:
        session = CallSession(call_sid=call_sid)
        self.save_session(session)
        return session

    def get_session(self, session_id: str) -> CallSession | None:
        with self._lock:
            row = self._connection.execute(
                "select payload from call_sessions where id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return CallSession.from_dict(json.loads(row["payload"]))

    def save_session(self, session: CallSession) -> None:
        payload = json.dumps(session.to_dict(), ensure_ascii=False)
        with self._lock:
            self._connection.execute(
                """
                insert into call_sessions (id, call_sid, status, updated_at, payload)
                values (?, ?, ?, ?, ?)
                on conflict(id) do update set
                    call_sid = excluded.call_sid,
                    status = excluded.status,
                    updated_at = excluded.updated_at,
                    payload = excluded.payload
                """,
                (
                    session.id,
                    session.call_sid,
                    session.status.value,
                    session.updated_at,
                    payload,
                ),
            )
            self._connection.commit()

    def list_sessions(self, limit: int = 50) -> list[CallSession]:
        with self._lock:
            rows = self._connection.execute(
                "select payload from call_sessions order by updated_at desc limit ?",
                (limit,),
            ).fetchall()
        return [CallSession.from_dict(json.loads(row["payload"])) for row in rows]

    def _ensure_schema(self) -> None:
        with self._lock:
            self._connection.execute(
                """
                create table if not exists call_sessions (
                    id text primary key,
                    call_sid text,
                    status text not null,
                    updated_at text not null,
                    payload text not null
                )
                """
            )
            self._connection.commit()

