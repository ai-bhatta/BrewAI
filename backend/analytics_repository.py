from __future__ import annotations

import json
import sqlite3
from pathlib import Path


class AnalyticsRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)

    def _connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=3)
        connection.row_factory = sqlite3.Row
        connection.execute(
            """CREATE TABLE IF NOT EXISTS analytics_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_name TEXT NOT NULL,
                session_id TEXT NOT NULL,
                player_id TEXT,
                game_mode TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                properties TEXT NOT NULL
            )"""
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS analytics_session_time ON analytics_events(session_id, timestamp)"
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS experiment_assignments (
                session_id TEXT NOT NULL,
                experiment_name TEXT NOT NULL,
                variant TEXT NOT NULL,
                assigned_at TEXT NOT NULL,
                PRIMARY KEY(session_id, experiment_name)
            )"""
        )
        return connection

    def record_event(self, event: dict) -> None:
        connection = self._connect()
        try:
            connection.execute(
                "INSERT INTO analytics_events(event_name,session_id,player_id,game_mode,timestamp,properties) VALUES(?,?,?,?,?,?)",
                (
                    event["event_name"], event["session_id"], event.get("player_id"),
                    event["game_mode"], event["timestamp"],
                    json.dumps(event["properties"], ensure_ascii=False, separators=(",", ":")),
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def load_events(self) -> list[dict]:
        connection = self._connect()
        try:
            rows = connection.execute("SELECT * FROM analytics_events ORDER BY timestamp,id").fetchall()
            events = []
            for row in rows:
                try:
                    events.append({
                        "event_name": row["event_name"], "session_id": row["session_id"],
                        "player_id": row["player_id"], "game_mode": row["game_mode"],
                        "timestamp": row["timestamp"], "properties": json.loads(row["properties"]),
                    })
                except (ValueError, TypeError):
                    continue
            return events
        finally:
            connection.close()

    def assignment(self, session_id: str, experiment: str, suggested_variant: str, assigned_at: str) -> str:
        connection = self._connect()
        try:
            connection.execute(
                "INSERT OR IGNORE INTO experiment_assignments(session_id,experiment_name,variant,assigned_at) VALUES(?,?,?,?)",
                (session_id, experiment, suggested_variant, assigned_at),
            )
            connection.commit()
            row = connection.execute(
                "SELECT variant FROM experiment_assignments WHERE session_id=? AND experiment_name=?",
                (session_id, experiment),
            ).fetchone()
            return row["variant"]
        finally:
            connection.close()

    def load_assignments(self) -> list[dict]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT session_id,experiment_name,variant,assigned_at FROM experiment_assignments"
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            connection.close()

    def reset(self) -> None:
        connection = self._connect()
        try:
            connection.execute("DELETE FROM analytics_events")
            connection.execute("DELETE FROM experiment_assignments")
            connection.commit()
        finally:
            connection.close()
