"""Synthetic sanity simulation only; results are not evidence about real players."""

import argparse
import json
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from bandit_repository import BanditRepository
from bandit_service import BanditService, DIFFICULTIES

PROFILES = {
    "beginner": {"skill": 0.35, "speed": 20, "hints": 0.45, "clarifications": 0.25},
    "average": {"skill": 0.58, "speed": 14, "hints": 0.22, "clarifications": 0.12},
    "expert": {"skill": 0.88, "speed": 7, "hints": 0.03, "clarifications": 0.02},
    "hint_dependent": {"skill": 0.57, "speed": 16, "hints": 0.75, "clarifications": 0.2},
    "slow_but_accurate": {"skill": 0.82, "speed": 25, "hints": 0.05, "clarifications": 0.05},
}


def simulate(rounds: int, seed: int) -> None:
    randomizer = random.Random(seed)
    with tempfile.TemporaryDirectory() as temporary:
        config_path = Path(temporary) / "bandit.json"
        config_path.write_text((ROOT / "data" / "bandit.json").read_text(encoding="utf-8"), encoding="utf-8")
        service = BanditService(BanditRepository(Path(temporary) / "bandit.sqlite3"), config_path, seed=seed)
        for profile_name, profile in PROFILES.items():
            current = "normal"
            totals = {"reward": 0.0, "correct": 0, "hints": 0, "decisions": 0}
            history = []
            for index in range(rounds):
                accuracy = sum(item["correct"] for item in history[-5:]) / max(1, len(history[-5:]))
                metrics = {
                    "recentAccuracy": accuracy,
                    "averageResponseTime": profile["speed"],
                    "hintOrderRatio": min(1, profile["hints"] * 1.25),
                    "clarificationOrderRatio": profile["clarifications"],
                    "currentStreak": min(5, sum(1 for item in reversed(history) if item["correct"])),
                }
                baseline_index = DIFFICULTIES.index(current)
                baseline = DIFFICULTIES[max(0, min(len(DIFFICULTIES) - 1, baseline_index + (1 if accuracy > 0.8 else -1 if accuracy < 0.45 else 0)))]
                decision = service.decide({"session_id": f"{profile_name}_session", "current_difficulty": current,
                                           "heuristic_action": baseline, "metrics": metrics})
                current = decision["chosen_difficulty"]
                level = DIFFICULTIES.index(current)
                probability = max(0.05, min(0.98, profile["skill"] - 0.055 * max(0, level - 1) + 0.025 * max(0, 1 - level)))
                correct = randomizer.random() < probability
                response = max(1, profile["speed"] + level * 0.8 + randomizer.uniform(-2, 2))
                hints = int(randomizer.random() < profile["hints"])
                clarifications = int(randomizer.random() < profile["clarifications"])
                outcome = service.complete({"decision_id": decision["decision_id"], "correct": correct,
                                            "response_time_seconds": response, "hints_used": hints,
                                            "clarifications_used": clarifications})
                totals["reward"] += outcome["reward"]
                totals["correct"] += int(correct)
                totals["hints"] += hints
                totals["decisions"] += 1
                history.append({"correct": correct})
            print(f"{profile_name}: orders={totals['decisions']} accuracy={totals['correct']/rounds:.2f} "
                  f"hints/order={totals['hints']/rounds:.2f} avg_reward={totals['reward']/rounds:.3f} "
                  f"final_difficulty={current}")
        print("Synthetic sanity output only; do not interpret as product or player evidence.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", type=int, default=25)
    parser.add_argument("--seed", type=int, default=41)
    arguments = parser.parse_args()
    simulate(max(1, arguments.rounds), arguments.seed)
