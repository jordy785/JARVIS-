"""Structured memory for JARVIS.

Persists:
- analyses / decisions
- trades (orders)
- positions
- performances / self-critic entries
- past macro events & observed impact
- backtest results
- model versions

Implemented as a thin SQLite-backed key-value + table store. Designed so that
JARVIS can answer questions like "Why did you take this trade?" or "Which macro
events impacted my trades the most?".
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jarvis.core.logging import get_logger

_log = get_logger("core.memory")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_events (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    ref_id TEXT,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memory_kind ON memory_events(kind);
CREATE INDEX IF NOT EXISTS idx_memory_ref ON memory_events(ref_id);
CREATE INDEX IF NOT EXISTS idx_memory_created ON memory_events(created_at);
"""

_Kinds = (
    "analysis",
    "decision",
    "order",
    "position_open",
    "position_close",
    "self_critic",
    "macro_event",
    "backtest_result",
    "paper_result",
    "live_result",
    "model_version",
    "learning_note",
)


class Memory:
    """Thread-safe SQLite memory store."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._conn() as c:
            c.executescript(_SCHEMA)
        _log.info("memory initialized at %s", self.db_path)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def record(self, kind: str, payload: dict[str, Any], ref_id: str | None = None) -> str:
        if kind not in _Kinds:
            raise ValueError(f"unknown memory kind: {kind}")
        eid = payload.get("id") or payload.get("order_id") or payload.get(
            "decision_id"
        ) or f"{kind}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO memory_events (id, kind, ref_id, payload, created_at) "
                "VALUES (?,?,?,?,?)",
                (
                    str(eid),
                    kind,
                    ref_id,
                    json.dumps(payload, default=str),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        return str(eid)

    def get(self, kind: str, eid: str) -> dict[str, Any] | None:
        with self._lock, self._conn() as c:
            row = c.execute(
                "SELECT payload FROM memory_events WHERE kind=? AND id=?", (kind, eid)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def query(
        self,
        kind: str | None = None,
        ref_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        sql = "SELECT payload FROM memory_events WHERE 1=1"
        params: list[Any] = []
        if kind:
            sql += " AND kind=?"
            params.append(kind)
        if ref_id:
            sql += " AND ref_id=?"
            params.append(ref_id)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._lock, self._conn() as c:
            rows = c.execute(sql, params).fetchall()
        return [json.loads(r[0]) for r in rows]

    # ---- High-level helpers for the chat/dashboard ----
    def recent_decisions(self, limit: int = 10) -> list[dict[str, Any]]:
        return self.query("decision", limit=limit)

    def recent_orders(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.query("order", limit=limit)

    def model_versions(self) -> list[dict[str, Any]]:
        return self.query("model_version", limit=50)

    def self_critic_entries(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.query("self_critic", limit=limit)

    def macro_events(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.query("macro_event", limit=limit)

    def backtest_results(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.query("backtest_result", limit=limit)

    def stats(self) -> dict[str, int]:
        with self._lock, self._conn() as c:
            rows = c.execute(
                "SELECT kind, COUNT(*) FROM memory_events GROUP BY kind"
            ).fetchall()
        return {k: v for k, v in rows}


# Singleton accessor
_memory: Memory | None = None


def get_memory() -> Memory:
    global _memory
    if _memory is None:
        from jarvis.core.config import get_settings

        s = get_settings()
        _memory = Memory(s.resolve_path(s.memory_db))
    return _memory


def reset_memory_for_tests(db_path: str | Path) -> Memory:
    """Replace the singleton with an in-memory or temp DB for tests."""
    global _memory
    _memory = Memory(db_path)
    return _memory
