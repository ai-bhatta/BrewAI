import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from analytics_repository import AnalyticsRepository
from analytics_service import AnalyticsService, AnalyticsValidationError


class AnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repository = AnalyticsRepository(self.root / "analytics.sqlite3")
        self.config_path = self.root / "experiments.json"
        self.config_path.write_text((ROOT / "data" / "experiments.json").read_text(encoding="utf-8"), encoding="utf-8")
        self.service = AnalyticsService(self.repository, self.config_path)

    def tearDown(self):
        self.temp.cleanup()

    def event(self, name, session="session_00000001", mode="game", properties=None, player="player_00000001"):
        self.service.record_event({
            "event_name": name,
            "session_id": session,
            "player_id": player,
            "game_mode": mode,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "properties": properties or {},
        })

    def test_events_are_stored_with_anonymous_ids_and_unapproved_properties_are_dropped(self):
        self.event("session_started", properties={"source": "local_browser", "player_name": "private"})
        self.event("ai_lab_example_loaded", properties={"source": "robustness", "example": "private request text"})
        stored = self.repository.load_events()[0]
        self.assertEqual(stored["session_id"], "session_00000001")
        self.assertEqual(stored["properties"], {"source": "local_browser"})
        self.assertNotIn("private", json.dumps(self.repository.load_events()))

    def test_malformed_events_and_unknown_names_are_rejected(self):
        with self.assertRaises(AnalyticsValidationError):
            self.service.record_event({"event_name": "unknown_event", "session_id": "session_00000001", "timestamp": "bad", "properties": {}})
        with self.assertRaises(AnalyticsValidationError):
            self.service.record_event({"event_name": "session_started", "session_id": "short", "timestamp": "bad", "properties": {}})
        with self.assertRaises(AnalyticsValidationError):
            self.service.record_event({"event_name": "session_started", "session_id": "session_00000001", "timestamp": "bad", "properties": {}})

    def test_experiment_assignment_is_deterministic_and_persisted_per_session(self):
        first = self.service.configuration_for_session("session_00000001")
        again = self.service.configuration_for_session("session_00000001")
        self.assertEqual(first["assignments"], again["assignments"])
        self.assertEqual(first["feature_flags"], again["feature_flags"])
        for name in first["assignments"]:
            self.repository.assignment("session_00000002", name, "A", datetime.now(timezone.utc).isoformat())
        persisted = self.service.configuration_for_session("session_00000002")
        self.assertTrue(all(variant == "A" for variant in persisted["assignments"].values()))

    def test_gameplay_summary_calculates_completion_accuracy_errors_and_usage(self):
        sid = "session_00000001"
        self.event("session_started", sid, properties={"source": "local_browser"})
        self.event("session_ended", sid, properties={"duration_seconds": 90})
        self.event("game_started", sid, "rush_hour", {"player_count": 1})
        self.event("round_started", sid, "rush_hour", {"difficulty": "normal"})
        self.event("customer_received", sid, "rush_hour", {"difficulty": "normal", "confidence_available": True})
        self.event("drink_submitted", sid, "rush_hour", {
            "difficulty": "normal", "correct": False, "accuracy": 0.8, "model_accuracy": 0.8,
            "response_time_seconds": 8, "points_awarded": 75, "mistake_attributes": ["topping"],
            "model_failure_attributes": ["milk"], "hints_used": 1, "clarifications_used": 1,
            "low_confidence": True,
        })
        self.event("customer_received", sid, "rush_hour", {"difficulty": "normal", "confidence_available": True})
        self.event("drink_submitted", sid, "rush_hour", {
            "difficulty": "normal", "correct": True, "accuracy": 1, "model_accuracy": 1,
            "response_time_seconds": 10, "points_awarded": 120, "mistake_attributes": [],
            "model_failure_attributes": [], "hints_used": 0, "clarifications_used": 0,
            "low_confidence": False,
        })
        self.event("order_correct", sid, "rush_hour", {"difficulty": "normal"})
        self.event("hint_requested", sid, "rush_hour", {"level": 1, "attribute": "milk", "cost": 1, "difficulty": "normal"})
        self.event("clarification_requested", sid, "rush_hour", {"attribute": "topping", "time_penalty": 3, "difficulty": "normal"})
        self.event("round_completed", sid, "rush_hour", {"difficulty": "normal", "score": 195, "orders_attempted": 2, "orders_correct": 1, "customers_lost": 0, "duration_seconds": 30})
        self.event("ai_lab_analysis_run", sid, "ai_lab", {"hasGroundTruth": False, "model_count": 4, "disagreement_count": 2})

        summary = self.service.summary()
        self.assertEqual(summary["engagement"]["total_sessions"], 1)
        self.assertEqual(summary["engagement"]["rush_hour_completion_rate"], 1)
        self.assertEqual(summary["gameplay"]["order_accuracy"], 0.5)
        self.assertEqual(summary["gameplay"]["hint_usage_rate"], 0.5)
        self.assertEqual(summary["gameplay"]["clarification_usage_rate"], 0.5)
        self.assertEqual(summary["ai_quality"]["model_failure_by_attribute"]["milk"], 1)
        self.assertEqual(summary["ai_quality"]["player_error_by_attribute"]["topping"], 1)
        self.assertEqual(summary["ai_quality"]["model_prediction_accuracy"], 0.9)
        self.assertEqual(summary["ai_quality"]["model_disagreement_frequency"], 1)
        difficulty = summary["difficulty"]["normal"]
        self.assertEqual(difficulty["success_rate"], 0.5)
        self.assertEqual(difficulty["hint_usage_rate"], 0.5)
        self.assertEqual(difficulty["clarification_usage_rate"], 0.5)

    def test_experiment_metrics_compare_variants_and_small_samples_are_exploratory(self):
        for session, variant, score, completed in (("session_variant_a", "A", 0, False), ("session_variant_b", "B", 120, True)):
            self.repository.assignment(session, "timer_seconds", variant, datetime.now(timezone.utc).isoformat())
            self.event("game_started", session, "game", {"player_count": 1})
            self.event("round_started", session, "game", {"difficulty": "normal"})
            if completed:
                self.event("round_completed", session, "game", {"difficulty": "normal", "score": score, "orders_attempted": 1, "orders_correct": 1, "customers_lost": 0, "duration_seconds": 30})
            else:
                self.event("round_failed", session, "game", {"difficulty": "normal", "failure_type": "no_orders_attempted", "orders_attempted": 0, "duration_seconds": 30})
        result = self.service.experiments()["experiments"]["timer_seconds"]
        self.assertEqual(result["variants"]["A"]["sessions"], 1)
        self.assertEqual(result["variants"]["B"]["sessions"], 1)
        self.assertEqual(result["variants"]["A"]["completion_rate"], 0)
        self.assertEqual(result["variants"]["B"]["completion_rate"], 1)
        self.assertEqual(result["primary_metric_delta"], 1)
        self.assertEqual(result["status"], "exploratory")
        self.assertIn("Insufficient data", result["sample_warning"])

    def test_adaptive_policy_experiment_compares_heuristic_and_bandit(self):
        for session, variant, policy, correct, hints in (
            ("session_policy_a", "A", "heuristic", True, 1),
            ("session_policy_b", "B", "contextual_bandit", True, 0),
        ):
            self.repository.assignment(session, "adaptive_policy", variant, datetime.now(timezone.utc).isoformat())
            self.event("game_started", session, "game", {"adaptive_difficulty": True, "adaptive_policy": policy})
            self.event("round_started", session, "game", {"difficulty": "normal"})
            self.event("drink_submitted", session, "game", {
                "difficulty": "normal", "correct": correct, "hints_used": hints,
                "clarifications_used": 0, "response_time_seconds": 8,
            })
            self.event("round_completed", session, "game", {
                "difficulty": "normal", "score": 100, "orders_attempted": 1,
                "orders_correct": 1, "customers_lost": 0, "duration_seconds": 30,
            })
        result = self.service.experiments()["experiments"]["adaptive_policy"]
        self.assertEqual(result["variants"]["A"]["successful_orders_without_hints_rate"], 0)
        self.assertEqual(result["variants"]["B"]["successful_orders_without_hints_rate"], 1)
        self.assertEqual(result["primary_metric_delta"], 1)
        self.assertIn("clarification_usage_rate", result["guardrail_metrics"])

    def test_adaptive_policy_decisions_are_accepted_as_analytics_events(self):
        self.event("adaptive_policy_decision", properties={
            "policy": "contextual_bandit", "mode": "exploration",
            "action": "normal", "estimated_reward": 0.2,
        })
        self.assertEqual(self.repository.load_events()[0]["properties"]["mode"], "exploration")

    def test_reset_only_clears_analytics_not_feedback_dataset_or_model(self):
        feedback_path = self.root / "feedback.sqlite3"
        connection = sqlite3.connect(feedback_path)
        connection.execute("CREATE TABLE feedback(id TEXT)")
        connection.execute("INSERT INTO feedback VALUES('keep-me')")
        connection.commit()
        connection.close()
        source_hash = hashlib.sha256((ROOT / "data" / "order_dataset.json").read_bytes()).hexdigest()
        model_path = ROOT / "backend" / "model" / "order_parser.joblib"
        model_hash = hashlib.sha256(model_path.read_bytes()).hexdigest()
        self.event("session_started")
        self.service.configuration_for_session("session_00000001")
        self.repository.reset()
        self.assertEqual(self.repository.load_events(), [])
        self.assertEqual(self.repository.load_assignments(), [])
        connection = sqlite3.connect(feedback_path)
        try:
            self.assertEqual(connection.execute("SELECT id FROM feedback").fetchone()[0], "keep-me")
        finally:
            connection.close()
        self.assertEqual(hashlib.sha256((ROOT / "data" / "order_dataset.json").read_bytes()).hexdigest(), source_hash)
        self.assertEqual(hashlib.sha256(model_path.read_bytes()).hexdigest(), model_hash)

    def test_csv_and_json_exports_are_local_and_machine_readable(self):
        self.event("session_started", properties={"source": "local_browser"})
        csv_text, csv_type = self.service.export("csv")
        json_text, json_type = self.service.export("json")
        self.assertEqual(csv_type, "text/csv")
        self.assertIn("session_id", csv_text)
        self.assertEqual(json_type, "application/json")
        self.assertEqual(json.loads(json_text)[0]["event_name"], "session_started")

    def test_analytics_api_handlers_cover_event_summary_experiments_export_and_reset(self):
        import main
        from schemas import AnalyticsEventRequest

        original_service = main.analytics_service
        main.analytics_service = self.service
        payload = AnalyticsEventRequest(
            event_name="session_started",
            session_id="session_00000001",
            game_mode="none",
            timestamp=datetime.now(timezone.utc).isoformat(),
            properties={"source": "local_browser"},
        )
        try:
            self.assertTrue(main.record_analytics_event(payload)["accepted"])
            self.assertEqual(main.analytics_summary().events_recorded, 1)
            self.assertIn("timer_seconds", main.analytics_experiments().experiments)
            self.assertIn(b"session_id", main.export_analytics("csv").body)
            self.assertTrue(main.reset_analytics()["reset"])
        finally:
            main.analytics_service = original_service


if __name__ == "__main__":
    unittest.main()
