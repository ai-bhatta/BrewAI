from __future__ import annotations

import sqlite3
from pathlib import Path


class CustomerGenerationRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)

    def _connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=3)
        connection.execute(
            """CREATE TABLE IF NOT EXISTS customer_generation_cache (
                cache_key TEXT PRIMARY KEY, request_text TEXT NOT NULL,
                model TEXT NOT NULL, created_at TEXT NOT NULL
            )"""
        )
        return connection

    def get(self, cache_key: str) -> str | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT request_text FROM customer_generation_cache WHERE cache_key=?", (cache_key,)
            ).fetchone()
            return row[0] if row else None
        finally:
            connection.close()

    def put(self, cache_key: str, request_text: str, model: str, created_at: str) -> None:
        connection = self._connect()
        try:
            connection.execute(
                "INSERT OR IGNORE INTO customer_generation_cache VALUES(?,?,?,?)",
                (cache_key, request_text, model, created_at),
            )
            connection.commit()
        finally:
            connection.close()

    def reset(self) -> None:
        connection = self._connect()
        try:
            connection.execute("DELETE FROM customer_generation_cache")
            connection.commit()
        finally:
            connection.close()
