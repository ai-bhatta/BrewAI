from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path


class BanditRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)

    def _connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=3)
        connection.row_factory = sqlite3.Row
        connection.execute(
            """CREATE TABLE IF NOT EXISTS bandit_decisions (
                decision_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, player_id TEXT,
                context TEXT NOT NULL, chosen_action TEXT NOT NULL, current_difficulty TEXT NOT NULL,
                selection_mode TEXT NOT NULL, policy TEXT NOT NULL, estimated_reward REAL,
                reward REAL, correct INTEGER, customer_lost INTEGER, timestamp TEXT NOT NULL
            )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS bandit_action_models (
                action TEXT PRIMARY KEY, weights TEXT NOT NULL, observations INTEGER NOT NULL
            )"""
        )
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def observation_count(self) -> int:
        with self._connection() as connection:
            return connection.execute("SELECT COUNT(*) FROM bandit_decisions WHERE reward IS NOT NULL").fetchone()[0]

    def get_model(self, action: str, dimensions: int) -> tuple[list[float], int]:
        with self._connection() as connection:
            row = connection.execute("SELECT weights,observations FROM bandit_action_models WHERE action=?", (action,)).fetchone()
            if not row:
                return [0.0] * dimensions, 0
            weights = json.loads(row["weights"])
            return (weights if len(weights) == dimensions else [0.0] * dimensions), row["observations"]

    def save_decision(self, decision: dict) -> None:
        with self._connection() as connection:
            connection.execute(
                """INSERT INTO bandit_decisions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (decision["decision_id"], decision["session_id"], decision.get("player_id"),
                 json.dumps(decision["context"], separators=(",", ":")), decision["chosen_action"],
                 decision["current_difficulty"], decision["selection_mode"], decision["policy"],
                 decision.get("estimated_reward"), None, None, None, decision["timestamp"]),
            )

    def complete_decision(self, decision_id: str, reward: float, correct: bool, customer_lost: bool, learning_rate: float) -> dict | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM bandit_decisions WHERE decision_id=?", (decision_id,)).fetchone()
            if not row or row["reward"] is not None:
                return None
            context = json.loads(row["context"])
            action = row["chosen_action"]
            model_row = connection.execute("SELECT weights,observations FROM bandit_action_models WHERE action=?", (action,)).fetchone()
            weights = json.loads(model_row["weights"]) if model_row else [0.0] * len(context)
            observations = model_row["observations"] if model_row else 0
            prediction = sum(weight * value for weight, value in zip(weights, context))
            error = reward - prediction
            updated = [weight + learning_rate * error * value for weight, value in zip(weights, context)]
            connection.execute(
                "UPDATE bandit_decisions SET reward=?,correct=?,customer_lost=? WHERE decision_id=?",
                (reward, int(correct), int(customer_lost), decision_id),
            )
            connection.execute(
                "INSERT OR REPLACE INTO bandit_action_models(action,weights,observations) VALUES(?,?,?)",
                (action, json.dumps(updated, separators=(",", ":")), observations + 1),
            )
            return {"action": action, "context": context, "weights": updated, "observations": observations + 1,
                    "session_id": row["session_id"], "policy": row["policy"]}

    def load_decisions(self) -> list[dict]:
        with self._connection() as connection:
            return [dict(row) for row in connection.execute("SELECT * FROM bandit_decisions ORDER BY timestamp").fetchall()]

    def reset(self) -> None:
        with self._connection() as connection:
            connection.execute("DELETE FROM bandit_decisions")
            connection.execute("DELETE FROM bandit_action_models")
