from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class HistoryStore:
    def __init__(self, data_dir: Path) -> None:
        data_dir.mkdir(parents=True, exist_ok=True)
        self.path = data_dir / "history.sqlite3"
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._db:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute(
                """
                CREATE TABLE IF NOT EXISTS task_history (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    command TEXT NOT NULL,
                    action_json TEXT NOT NULL,
                    risk INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    result_json TEXT NOT NULL
                )
                """
            )

    def write(
        self,
        task_id: str,
        command: str,
        action: dict[str, Any],
        risk: int,
        status: str,
        result: dict[str, Any] | None = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._db:
            self._db.execute(
                """
                INSERT INTO task_history
                    (id, created_at, command, action_json, risk, status, result_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status,
                    result_json=excluded.result_json
                """,
                (
                    task_id,
                    now,
                    command,
                    json.dumps(action, ensure_ascii=False),
                    risk,
                    status,
                    json.dumps(result or {}, ensure_ascii=False),
                ),
            )

    def recent(self, limit: int = 30) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 100))
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM task_history ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            {
                "id": row["id"],
                "created_at": row["created_at"],
                "command": row["command"],
                "action": json.loads(row["action_json"]),
                "risk": row["risk"],
                "status": row["status"],
                "result": json.loads(row["result_json"]),
            }
            for row in rows
        ]

    def clear(self) -> None:
        with self._lock, self._db:
            self._db.execute("DELETE FROM task_history")
