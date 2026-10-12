import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from analytics_repository import AnalyticsRepository
from bandit_repository import BanditRepository
from bandit_service import BanditService, DIFFICULTIES


class BanditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = json.loads((ROOT / "data" / "bandit.json").read_text(encoding="utf-8"))
        self.config_path = self.root / "bandit.json"
        self.write_config()
        self.repository = BanditRepository(self.root / "bandit.sqlite3")
        self.service = BanditService(self.repository, self.config_path, seed=13)

    def tearDown(self):
        self.temp.cleanup()

    def write_config(self):
        self.config_path.write_text(json.dumps(self.config), encoding="utf-8")

    def payload(self, **updates):
        payload = {"session_id": "session_00000001", "player_id": "session_00000001_p1",
                   "current_difficulty": "normal", "heuristic_action": "ambiguous",
                   "metrics": {"recentAccuracy": 0.8, "averageResponseTime": 12,
                               "hintOrderRatio": 0.2, "clarificationOrderRatio": 0,
                               "currentStreak": 2}}
        payload.update(updates)
        return payload

    def test_context_generation_is_normalized_and_deterministic(self):
        metrics = self.payload()["metrics"]
        self.assertEqual(self.service.build_context(metrics, "normal"), self.service.build_context(metrics, "normal"))
        self.assertEqual(len(self.service.build_context(metrics, "normal")), 8)
        self.assertEqual(self.service.build_context(metrics, "normal")[1], 0.8)

    def test_cold_start_uses_the_heuristic_and_respects_one_step(self):
        result = self.service.decide(self.payload(current_difficulty="easy", heuristic_action="multi_clue"))
        self.assertEqual(result["mode"], "heuristic_fallback")
        self.assertEqual(result["chosen_difficulty"], "normal")

    def test_exploration_is_seeded_and_limited_to_neighbor_actions(self):
        self.config["minimum_bandit_observations"] = 0
        self.config["epsilon"] = 1
        self.write_config()
        first = self.service.decide(self.payload())
        other_repo = BanditRepository(self.root / "other.sqlite3")
        other_service = BanditService(other_repo, self.config_path, seed=13)
        second = other_service.decide(self.payload())
        self.assertEqual(first["mode"], "exploration")
        self.assertEqual(first["chosen_difficulty"], second["chosen_difficulty"])
        self.assertIn(first["chosen_difficulty"], {"easy", "normal", "ambiguous"})

    def test_reward_balances_success_speed_hints_and_clarification(self):
        reward = self.service.calculate_reward({"correct": True, "response_time_seconds": 10,
                                                "hints_used": 1, "clarifications_used": 1}, self.config)
        self.assertEqual(reward, 0.69)
        trivial = self.service.calculate_reward({"correct": True, "response_time_seconds": 2}, self.config)
        self.assertEqual(trivial, 0.5)
        lost = self.service.calculate_reward({"customer_lost": True}, self.config)
        self.assertEqual(lost, -0.8)

    def test_outcome_updates_only_after_result_and_duplicate_outcomes_are_ignored(self):
        decision = self.service.decide(self.payload())
        self.assertEqual(self.repository.observation_count(), 0)
        payload = {"decision_id": decision["decision_id"], "correct": True,
                   "response_time_seconds": 10, "hints_used": 0, "clarifications_used": 0}
        result = self.service.complete(payload)
        self.assertTrue(result["updated"])
        self.assertEqual(self.repository.observation_count(), 1)
        self.assertFalse(self.service.complete(payload)["updated"])

    def test_policy_decisions_and_model_parameters_persist(self):
        decision = self.service.decide(self.payload())
        self.service.complete({"decision_id": decision["decision_id"], "correct": True,
                               "response_time_seconds": 10})
        reopened = BanditService(BanditRepository(self.root / "bandit.sqlite3"), self.config_path, seed=13)
        self.assertEqual(reopened.metrics()["completed_observations"], 1)
        weights, observations = reopened.repository.get_model(decision["chosen_difficulty"], 8)
        self.assertEqual(observations, 1)
        self.assertNotEqual(weights, [0.0] * 8)

    def test_reset_removes_bandit_state_but_keeps_game_analytics(self):
        analytics = AnalyticsRepository(self.root / "analytics.sqlite3")
        analytics.record_event({"event_name": "session_started", "session_id": "session_00000001",
                                "player_id": None, "game_mode": "none", "timestamp": "2026-01-01T00:00:00+00:00",
                                "properties": {}})
        decision = self.service.decide(self.payload())
        self.service.reset()
        self.assertEqual(self.service.metrics()["decisions"], 0)
        self.assertEqual(len(analytics.load_events()), 1)

    def test_invalid_personal_identifier_is_rejected(self):
        with self.assertRaises(ValueError):
            self.service.decide(self.payload(session_id="Player Amy"))

    def test_api_handlers_support_decision_outcome_metrics_and_reset(self):
        import main
        from schemas import BanditDecisionRequest, BanditOutcomeRequest

        original_service = main.bandit_service
        main.bandit_service = self.service
        try:
            decision = main.bandit_decision(BanditDecisionRequest(**self.payload()))
            outcome = main.bandit_outcome(BanditOutcomeRequest(
                decision_id=decision["decision_id"], correct=True, response_time_seconds=10,
            ))
            self.assertTrue(outcome["updated"])
            self.assertEqual(main.bandit_metrics()["completed_observations"], 1)
            self.assertTrue(main.reset_bandit()["reset"])
        finally:
            main.bandit_service = original_service


if __name__ == "__main__":
    unittest.main()
