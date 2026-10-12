from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FeedbackRepository:
    """Small SQLite boundary for untrusted and reviewed human corrections."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)

    def _connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute(
            """CREATE TABLE IF NOT EXISTS feedback (
                id TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                normalized_text TEXT NOT NULL,
                model TEXT NOT NULL,
                prediction TEXT NOT NULL,
                corrected TEXT NOT NULL,
                confidence TEXT,
                source TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('pending','approved','rejected','used_for_training')),
                created_at TEXT NOT NULL,
                reviewed_at TEXT,
                model_disagreement INTEGER NOT NULL DEFAULT 0,
                low_confidence INTEGER NOT NULL DEFAULT 0,
                priority INTEGER NOT NULL DEFAULT 3
            )"""
        )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS feedback_exact_correction "
            "ON feedback(normalized_text, corrected)"
        )
        return connection

    @staticmethod
    def _decode(row: sqlite3.Row) -> Optional[dict]:
        try:
            prediction = json.loads(row["prediction"])
            corrected = json.loads(row["corrected"])
            confidence = json.loads(row["confidence"]) if row["confidence"] else None
            recipe_keys = {"base", "milk", "sweetness", "topping", "vibe"}
            if (
                not isinstance(row["text"], str)
                or not isinstance(prediction, dict)
                or set(prediction) != recipe_keys
                or not all(isinstance(value, str) for value in prediction.values())
                or not isinstance(corrected, dict)
                or set(corrected) != recipe_keys
                or not all(isinstance(value, str) for value in corrected.values())
                or (confidence is not None and not isinstance(confidence, dict))
                or (confidence is not None and set(confidence) - recipe_keys)
                or (confidence is not None and not all(
                    value is None or isinstance(value, (int, float)) and 0 <= value <= 1
                    for value in confidence.values()
                ))
            ):
                return None
            return {
                "id": row["id"],
                "text": row["text"],
                "model": row["model"],
                "predicted": prediction,
                "corrected": corrected,
                "confidence": confidence,
                "source": row["source"],
                "status": row["status"],
                "created_at": row["created_at"],
                "reviewed_at": row["reviewed_at"],
                "model_disagreement": bool(row["model_disagreement"]),
                "low_confidence": bool(row["low_confidence"]),
                "priority": row["priority"],
            }
        except (TypeError, ValueError, KeyError):
            return None

    def create(self, entry: dict) -> tuple[dict, list[dict]]:
        normalized = " ".join(entry["text"].casefold().split())
        correction_json = json.dumps(entry["corrected"], sort_keys=True, separators=(",", ":"))
        connection = self._connect()
        try:
            rows = connection.execute("SELECT * FROM feedback").fetchall()
            similar = []
            from difflib import SequenceMatcher

            for row in rows:
                existing = self._decode(row)
                if existing is None:
                    continue
                if row["normalized_text"] == normalized and row["corrected"] == correction_json:
                    raise DuplicateFeedbackError(existing["id"])
                ratio = SequenceMatcher(None, normalized, row["normalized_text"]).ratio()
                if ratio >= 0.88:
                    similar.append({"id": existing["id"], "text": existing["text"], "similarity": round(ratio, 3)})
            feedback_id = str(uuid4())
            created_at = utc_now()
            try:
                connection.execute(
                    """INSERT INTO feedback (
                    id,text,normalized_text,model,prediction,corrected,confidence,source,status,
                    created_at,model_disagreement,low_confidence,priority
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    feedback_id, entry["text"], normalized, entry["model"],
                    json.dumps(entry["predicted"], sort_keys=True), correction_json,
                    json.dumps(entry["confidence"], sort_keys=True) if entry["confidence"] is not None else None,
                    "ai_lab", "pending", created_at, int(entry["model_disagreement"]),
                    int(entry["low_confidence"]), entry["priority"],
                    ),
                )
            except sqlite3.IntegrityError as error:
                duplicate = connection.execute(
                    "SELECT id FROM feedback WHERE normalized_text=? AND corrected=?",
                    (normalized, correction_json),
                ).fetchone()
                if duplicate:
                    raise DuplicateFeedbackError(duplicate["id"]) from error
                raise
            connection.commit()
            result = {**entry, "id": feedback_id, "source": "ai_lab", "status": "pending", "created_at": created_at, "reviewed_at": None}
            return result, similar
        finally:
            connection.close()

    def list_entries(self, status: Optional[str] = "pending") -> list[dict]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT * FROM feedback WHERE status = ?" if status else "SELECT * FROM feedback",
                (status,) if status else (),
            ).fetchall()
            entries = [entry for row in rows if (entry := self._decode(row)) is not None]
            entries.sort(key=lambda entry: (entry["priority"], entry["created_at"]))
            return entries
        finally:
            connection.close()

    def review(self, feedback_id: str, status: str) -> Optional[dict]:
        connection = self._connect()
        try:
            row = connection.execute("SELECT * FROM feedback WHERE id = ?", (feedback_id,)).fetchone()
            if row is None or row["status"] != "pending":
                return None
            connection.execute(
                "UPDATE feedback SET status = ?, reviewed_at = ? WHERE id = ? AND status = 'pending'",
                (status, utc_now(), feedback_id),
            )
            connection.commit()
            updated = connection.execute("SELECT * FROM feedback WHERE id = ?", (feedback_id,)).fetchone()
            return self._decode(updated) if updated else None
        finally:
            connection.close()

    def approved_examples(self) -> list[dict]:
        return [
            {"id": entry["id"], "utterance": entry["text"], **entry["corrected"]}
            for entry in self.list_entries(status="approved")
            if isinstance(entry.get("corrected"), dict)
        ]


class DuplicateFeedbackError(ValueError):
    def __init__(self, existing_id: str) -> None:
        self.existing_id = existing_id
        super().__init__(f"An identical normalized request and correction already exists ({existing_id}).")
