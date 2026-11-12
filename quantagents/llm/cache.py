"""SQLite response cache (brief section 8). A hit returns the stored response with no API call.

The key is the SHA-256 of the full request (model, system prompt, messages, output schema,
thinking and effort settings, max_tokens) plus the replicate index and the attempt number.
The API key and key label are NOT part of it, so cached answers survive a key swap.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def request_key(request: dict, replicate: int = 0, attempt: int = 0) -> str:
    payload = json.dumps({"request": request, "replicate": int(replicate), "attempt": int(attempt)},
                         sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ResponseCache:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._con() as con:
            con.execute("""CREATE TABLE IF NOT EXISTS responses (
                key TEXT PRIMARY KEY, created_utc TEXT, model TEXT, response TEXT)""")

    @contextmanager
    def _con(self):
        con = sqlite3.connect(self.path)
        try:
            with con:
                yield con
        finally:
            con.close()

    def get(self, key: str) -> dict | None:
        with self._con() as con:
            row = con.execute("SELECT response FROM responses WHERE key = ?", [key]).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, key: str, model: str, response: dict) -> None:
        with self._con() as con:
            con.execute("INSERT OR REPLACE INTO responses VALUES (?, ?, ?, ?)",
                        [key, datetime.now(timezone.utc).isoformat(timespec="seconds"), model,
                         json.dumps(response, ensure_ascii=False)])

    def __len__(self) -> int:
        with self._con() as con:
            return con.execute("SELECT count(*) FROM responses").fetchone()[0]
