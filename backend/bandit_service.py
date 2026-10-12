from __future__ import annotations

import json
import random
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from bandit_repository import BanditRepository

ROOT_PATH = Path(__file__).resolve().parents[1]
DIFFICULTIES = ("easy", "normal", "ambiguous", "slang", "negation", "multi_clue")
FEATURES = ("recent_accuracy", "average_response_time", "hint_usage_rate", "clarification_usage_rate", "current_streak", "recent_error_rate", "current_difficulty")


class BanditService:
    def __init__(self, repository: BanditRepository | None = None, config_path: Path | None = None, seed: int | None = None) -> None:
        self.repository = repository or BanditRepository(ROOT_PATH / "data" / "bandit.sqlite3")
        self.config_path = Path(config_path or ROOT_PATH / "data" / "bandit.json")
        self.random = random.Random(seed)

    def config(self) -> dict:
        return json.loads(self.config_path.read_text(encoding="utf-8"))

    @staticmethod
    def build_context(metrics: dict, current_difficulty: str) -> list[float]:
        accuracy = min(1.0, max(0.0, float(metrics.get("recentAccuracy", 0))))
        response = min(30.0, max(0.0, float(metrics.get("averageResponseTime", 0)))) / 30.0
        hints = min(1.0, max(0.0, float(metrics.get("hintOrderRatio", 0))))
        clarifications = min(1.0, max(0.0, float(metrics.get("clarificationOrderRatio", 0))))
        streak = min(5.0, max(0.0, float(metrics.get("currentStreak", 0)))) / 5.0
        index = DIFFICULTIES.index(current_difficulty) if current_difficulty in DIFFICULTIES else 1
        return [1.0, accuracy, response, hints, clarifications, streak, 1.0 - accuracy, index / (len(DIFFICULTIES) - 1)]

    @staticmethod
    def _clamp_action(action: str, current: str) -> str:
        current_index = DIFFICULTIES.index(current) if current in DIFFICULTIES else 1
        proposed = DIFFICULTIES.index(action) if action in DIFFICULTIES else current_index
        return DIFFICULTIES[min(current_index + 1, max(current_index - 1, proposed))]

    @staticmethod
    def calculate_reward(outcome: dict, config: dict) -> float:
        weights = config["reward"]
        correct = bool(outcome.get("correct"))
        lost = bool(outcome.get("customer_lost"))
        response = max(0.0, float(outcome.get("response_time_seconds", 0)))
        hints = min(3, max(0, int(outcome.get("hints_used", 0))))
        clarifications = min(3, max(0, int(outcome.get("clarifications_used", 0))))
        if lost:
            reward = weights["customer_lost"]
        elif correct:
            reward = weights["correct_order"]
            reward += weights["trivial_response"] if response <= weights["fast_seconds"] else (
                weights["reasonable_response"] if response <= weights["slow_seconds"] else 0
            )
            if response <= weights["fast_seconds"] and hints == 0 and clarifications == 0:
                reward += weights["trivial_order_penalty"]
        else:
            reward = weights["incorrect_order"]
        reward += hints * weights["hint_each"] + clarifications * weights["clarification_each"]
        return round(max(-1.0, min(1.0, reward)), 4)

    def decide(self, payload: dict) -> dict:
        if not isinstance(payload.get("session_id"), str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", payload["session_id"]):
            raise ValueError("An anonymous session ID is required.")
        if payload.get("player_id") is not None and not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", payload["player_id"]):
            raise ValueError("Player ID must be anonymous.")
        current = payload.get("current_difficulty", "normal")
        if current not in DIFFICULTIES:
            current = "normal"
        baseline = self._clamp_action(payload.get("heuristic_action", current), current)
        context = self.build_context(payload.get("metrics", {}), current)
        config = self.config()
        count = self.repository.observation_count()
        current_index = DIFFICULTIES.index(current)
        actions = DIFFICULTIES[max(0, current_index - 1): current_index + 2]
        scores = {}
        for action in actions:
            weights, _ = self.repository.get_model(action, len(context))
            scores[action] = round(sum(a * b for a, b in zip(weights, context)), 4)
        if count < config["minimum_bandit_observations"]:
            action, mode, reason = baseline, "heuristic_fallback", "cold_start_heuristic"
            estimated = scores.get(action, 0.0)
        elif self.random.random() < config["epsilon"]:
            action, mode, reason = self.random.choice(actions), "exploration", "epsilon_exploration"
            estimated = scores[action]
        else:
            action = max(actions, key=lambda item: (scores[item], -actions.index(item)))
            mode, reason, estimated = "exploitation", "highest_estimated_reward", scores[action]
        decision = {
            "decision_id": str(uuid.uuid4()), "session_id": payload["session_id"],
            "player_id": payload.get("player_id"), "context": context,
            "chosen_action": action, "current_difficulty": current,
            "selection_mode": mode, "policy": "contextual_bandit",
            "estimated_reward": estimated, "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.repository.save_decision(decision)
        return {"decision_id": decision["decision_id"], "chosen_difficulty": action, "policy": "contextual_bandit",
                "mode": mode, "reason": reason,
                "estimated_reward": estimated, "action_scores": scores, "context": context,
                "observations": count, "minimum_observations": config["minimum_bandit_observations"]}

    def complete(self, payload: dict) -> dict:
        config = self.config()
        reward = self.calculate_reward(payload, config)
        updated = self.repository.complete_decision(
            payload["decision_id"], reward, bool(payload.get("correct")), bool(payload.get("customer_lost")),
            float(config.get("learning_rate", 0.08)),
        )
        if updated is None:
            return {"updated": False, "reward": reward}
        return {"updated": True, "reward": reward, "action": updated["action"], "observations": updated["observations"]}

    def metrics(self) -> dict:
        rows = self.repository.load_decisions()
        completed = [row for row in rows if row["reward"] is not None]
        by_action = {}
        for action in DIFFICULTIES:
            subset = [row for row in completed if row["chosen_action"] == action]
            by_action[action] = {"decisions": sum(row["chosen_action"] == action for row in rows),
                                 "average_reward": round(sum(row["reward"] for row in subset) / len(subset), 4) if subset else 0,
                                 "completion_rate": round(sum(bool(row["correct"]) for row in subset) / len(subset), 4) if subset else 0}
        modes = [row for row in completed if row["selection_mode"] in {"exploration", "exploitation"}]
        return {"decisions": len(rows), "completed_observations": len(completed),
                "exploration_rate": round(sum(row["selection_mode"] == "exploration" for row in modes) / len(modes), 4) if modes else 0,
                "average_reward": round(sum(row["reward"] for row in completed) / len(completed), 4) if completed else 0,
                "reward_by_difficulty": {action: by_action[action]["average_reward"] for action in DIFFICULTIES},
                "action_distribution": {action: by_action[action]["decisions"] for action in DIFFICULTIES},
                "completion_by_action": {action: by_action[action]["completion_rate"] for action in DIFFICULTIES},
                "actions": by_action}

    def reset(self) -> None:
        self.repository.reset()
