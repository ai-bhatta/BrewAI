from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

from analytics_repository import AnalyticsRepository

ROOT_PATH = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT_PATH / "data" / "experiments.json"
DATABASE_PATH = ROOT_PATH / "data" / "analytics.sqlite3"
ATTRIBUTES = ("base", "milk", "sweetness", "topping", "vibe")
MODES = {"game", "rush_hour", "ai_lab", "analytics", "none"}
EVENT_PROPERTIES = {
    "session_started": {"source"},
    "session_ended": {"duration_seconds"},
    "game_started": {"player_count", "difficulty", "adaptive_difficulty", "adaptive_policy", "timer_seconds"},
    "round_started": {"difficulty", "round_number"},
    "round_completed": {"difficulty", "score", "orders_attempted", "orders_correct", "customers_lost", "duration_seconds"},
    "round_failed": {"difficulty", "failure_type", "orders_attempted", "duration_seconds"},
    "customer_received": {"difficulty", "persona", "confidence_available", "model_source", "generation_source"},
    "generation_requested": {"mode", "context"},
    "generation_succeeded": {"source", "cache_hit", "latency_ms", "context"},
    "generation_failed": {"reason", "latency_ms", "context"},
    "generation_fallback": {"reason", "source", "context"},
    "generation_latency": {"source", "latency_ms", "context"},
    "generation_source": {"source", "context"},
    "drink_submitted": {"difficulty", "correct", "accuracy", "model_accuracy", "response_time_seconds", "points_awarded", "mistake_attributes", "model_failure_attributes", "hints_used", "clarifications_used", "low_confidence", "model_disagreement"},
    "order_correct": {"difficulty", "response_time_seconds"},
    "order_failed": {"difficulty", "failure_type", "response_time_seconds", "hints_used", "clarifications_used"},
    "next_round": {"difficulty", "game_mode"},
    "hint_requested": {"level", "attribute", "cost", "difficulty"},
    "clarification_requested": {"attribute", "time_penalty", "difficulty"},
    "difficulty_evaluated": {"previous_difficulty", "new_difficulty", "difficulty_reason"},
    "difficulty_changed": {"previous_difficulty", "new_difficulty", "difficulty_reason"},
    "ai_lab_opened": set(),
    "ai_lab_analysis_run": {"hasGroundTruth", "model_count", "disagreement_count"},
    "ai_lab_analysis_started": {"hasGroundTruth"},
    "ai_lab_example_loaded": {"source", "category", "difficulty"},
    "ai_lab_model_failure": {"model"},
    "feedback_submitted": {"model"},
    "feedback_approved": set(),
    "feedback_rejected": set(),
    "candidate_training_completed": {"model", "feedback_examples", "regression_count"},
    "analytics_view_opened": set(),
    "adaptive_policy_decision": {"policy", "mode", "action", "current_difficulty", "estimated_reward", "reason"},
    "adaptive_policy_outcome": {"policy", "action", "difficulty", "reward", "correct", "customer_lost", "response_time_seconds"},
    "adaptive_policy_update_failed": set(),
}
VALID_DIFFICULTIES = {"easy", "normal", "ambiguous", "slang", "negation", "multi_clue"}
IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]{8,80}$")
MINIMUM_VARIANT_SESSIONS = 10


class AnalyticsValidationError(ValueError):
    pass


class AnalyticsService:
    def __init__(self, repository: AnalyticsRepository | None = None, config_path: Path = CONFIG_PATH) -> None:
        self.repository = repository or AnalyticsRepository(DATABASE_PATH)
        self.config_path = Path(config_path)

    def load_config(self) -> dict:
        with self.config_path.open("r", encoding="utf-8") as handle:
            config = json.load(handle)
        if not isinstance(config.get("experiments"), dict):
            raise ValueError("Experiment configuration is malformed.")
        return config

    @staticmethod
    def _safe_value(value):
        if isinstance(value, (str, bool, int)):
            return value if not isinstance(value, str) or len(value) <= 120 else value[:120]
        if isinstance(value, float) and math.isfinite(value):
            return value
        if isinstance(value, list):
            return [item for item in value[:10] if isinstance(item, str) and len(item) <= 32]
        return None

    def record_event(self, payload: dict) -> None:
        name = payload.get("event_name")
        session_id = payload.get("session_id")
        mode = payload.get("game_mode", "none")
        if name not in EVENT_PROPERTIES:
            raise AnalyticsValidationError("Unknown analytics event.")
        if not isinstance(session_id, str) or not IDENTIFIER.fullmatch(session_id):
            raise AnalyticsValidationError("A valid anonymous session ID is required.")
        if mode not in MODES:
            raise AnalyticsValidationError("Unknown game mode.")
        raw_properties = payload.get("properties", {})
        if not isinstance(raw_properties, dict) or len(raw_properties) > 40:
            raise AnalyticsValidationError("Event properties must be a small object.")
        properties = {
            key: safe
            for key, value in raw_properties.items()
            if key in EVENT_PROPERTIES[name]
            and (safe := self._safe_value(value)) is not None
        }
        timestamp = payload.get("timestamp")
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError
        except (AttributeError, ValueError):
            raise AnalyticsValidationError("Event timestamp must be ISO-8601 with a timezone.")
        player_id = payload.get("player_id")
        if player_id is not None and (not isinstance(player_id, str) or not IDENTIFIER.fullmatch(player_id)):
            raise AnalyticsValidationError("Player ID must be anonymous and valid.")
        self.repository.record_event({
            "event_name": name,
            "session_id": session_id,
            "player_id": player_id,
            "game_mode": mode,
            "timestamp": parsed.astimezone(timezone.utc).isoformat(),
            "properties": properties,
        })

    def configuration_for_session(self, session_id: str) -> dict:
        if not isinstance(session_id, str) or not IDENTIFIER.fullmatch(session_id):
            raise AnalyticsValidationError("A valid anonymous session ID is required.")
        config = self.load_config()
        assignments = {}
        flags = {}
        for name, experiment in config["experiments"].items():
            variants = experiment.get("variants", {})
            if set(variants) != {"A", "B"}:
                raise ValueError(f"Experiment {name} must define A and B variants.")
            digest = hashlib.sha256(f"{name}:{session_id}".encode("utf-8")).digest()
            proposed = "A" if int.from_bytes(digest[:8], "big") % 2 == 0 else "B"
            variant = self.repository.assignment(
                session_id, name, proposed, datetime.now(timezone.utc).isoformat()
            )
            assignments[name] = variant
            flags[name] = variants[variant]["value"]
        return {
            "session_id": session_id,
            "assignments": assignments,
            "feature_flags": flags,
            "experiments": config["experiments"],
            "minimum_exploratory_sessions_per_variant": config.get(
                "minimum_exploratory_sessions_per_variant", MINIMUM_VARIANT_SESSIONS
            ),
        }

    @staticmethod
    def _average(values: list[float]) -> float:
        return round(mean(values), 3) if values else 0.0

    def summary(self) -> dict:
        events = self.repository.load_events()
        by_name = defaultdict(list)
        sessions = defaultdict(list)
        for event in events:
            by_name[event["event_name"]].append(event)
            sessions[event["session_id"]].append(event)

        started_sessions = [event for event in by_name["session_started"]]
        session_durations = [
            float(event["properties"].get("duration_seconds", 0))
            for event in by_name["session_ended"]
        ]
        rounds_per_session = [
            sum(event["event_name"] == "round_started" for event in session_events)
            for session_events in sessions.values()
            if any(event["event_name"] == "session_started" for event in session_events)
        ]
        submitted = by_name["drink_submitted"]
        order_failures = by_name["order_failed"]
        all_orders = submitted + order_failures
        correct_orders = by_name["order_correct"]
        rounds_started = by_name["round_started"]
        rush_started = [event for event in rounds_started if event["game_mode"] == "rush_hour"]
        rush_completed = [event for event in by_name["round_completed"] if event["game_mode"] == "rush_hour"]
        hints = by_name["hint_requested"]
        clarifications = by_name["clarification_requested"]
        scores = [float(event["properties"].get("score", 0)) for event in by_name["round_completed"]]
        response_times = [
            float(event["properties"].get("response_time_seconds", 0))
            for event in all_orders if "response_time_seconds" in event["properties"]
        ]
        player_errors = Counter()
        model_errors = Counter()
        difficulty_orders = defaultdict(list)
        for event in submitted:
            props = event["properties"]
            for attribute in props.get("mistake_attributes", []):
                if attribute in ATTRIBUTES:
                    player_errors[attribute] += 1
            for attribute in props.get("model_failure_attributes", []):
                if attribute in ATTRIBUTES:
                    model_errors[attribute] += 1
        for event in all_orders:
            difficulty = event["properties"].get("difficulty")
            if difficulty in VALID_DIFFICULTIES:
                difficulty_orders[difficulty].append(event)
        difficulty_metrics = {}
        for difficulty, rows in difficulty_orders.items():
            done = [row for row in rows if row["event_name"] == "drink_submitted"]
            difficulty_metrics[difficulty] = {
                "orders": len(rows),
                "success_rate": round(sum(bool(row["properties"].get("correct")) for row in done) / len(rows), 3) if rows else 0,
                "average_response_time_seconds": self._average([
                    float(row["properties"].get("response_time_seconds", 0)) for row in rows
                ]),
                "hint_usage_rate": round(sum(int(row["properties"].get("hints_used", 0)) > 0 for row in rows) / len(rows), 3) if rows else 0,
                "clarification_usage_rate": round(sum(int(row["properties"].get("clarifications_used", 0)) > 0 for row in rows) / len(rows), 3) if rows else 0,
            }

        funnel_names = ("session_started", "game_started", "customer_received", "drink_submitted", "order_correct", "next_round")
        funnel_counts = [
            (name, len({event["session_id"] for event in by_name[name]}))
            for name in funnel_names
        ]
        funnel = []
        previous = None
        for name, count in funnel_counts:
            funnel.append({"stage": name, "count": count, "conversion_rate": round(count / previous, 3) if previous else None})
            previous = count

        model_accuracies = [
            float(event["properties"]["model_accuracy"])
            for event in submitted if isinstance(event["properties"].get("model_accuracy"), (int, float))
        ]
        low_confidence_orders = sum(bool(event["properties"].get("low_confidence")) for event in submitted)
        disagreement_orders = sum(
            int(event["properties"].get("disagreement_count", 0)) > 0
            for event in by_name["ai_lab_analysis_run"]
        )
        feedback_submitted = len(by_name["feedback_submitted"])
        feedback_approved = len(by_name["feedback_approved"])
        feedback_rejected = len(by_name["feedback_rejected"])
        retraining_count = len(list((ROOT_PATH / "results").glob("feedback_retrain_*.json")))
        return {
            "engagement": {
                "total_sessions": len({event["session_id"] for event in started_sessions}),
                "average_session_duration_seconds": self._average(session_durations),
                "average_rounds_per_session": self._average(rounds_per_session),
                "rush_hour_completion_rate": round(len(rush_completed) / len(rush_started), 3) if rush_started else 0,
            },
            "gameplay": {
                "average_score": self._average(scores),
                "order_accuracy": round(sum(bool(event["properties"].get("correct")) for event in submitted) / len(submitted), 3) if submitted else 0,
                "average_response_time_seconds": self._average(response_times),
                "customers_lost": sum(event["properties"].get("failure_type") == "lost" for event in order_failures),
                "hint_usage_rate": round(sum(int(event["properties"].get("hints_used", 0)) > 0 for event in all_orders) / len(all_orders), 3) if all_orders else 0,
                "clarification_usage_rate": round(sum(int(event["properties"].get("clarifications_used", 0)) > 0 for event in all_orders) / len(all_orders), 3) if all_orders else 0,
            },
            "difficulty": difficulty_metrics,
            "ai_quality": {
                "model_prediction_accuracy": self._average(model_accuracies),
                "model_failure_by_attribute": {attribute: model_errors[attribute] for attribute in ATTRIBUTES},
                "player_error_by_attribute": {attribute: player_errors[attribute] for attribute in ATTRIBUTES},
                "low_confidence_prediction_rate": round(low_confidence_orders / len(submitted), 3) if submitted else 0,
                "model_disagreement_frequency": disagreement_orders,
                "evaluated_orders": len(model_accuracies),
            },
            "feedback": {
                "submitted": feedback_submitted,
                "approval_rate": round(feedback_approved / feedback_submitted, 3) if feedback_submitted else 0,
                "rejected": feedback_rejected,
                "candidate_retraining_count": retraining_count,
            },
            "funnel": funnel,
            "events_recorded": len(events),
        }

    def experiments(self) -> dict:
        config = self.load_config()
        assignments = self.repository.load_assignments()
        events = self.repository.load_events()
        experiments = {}
        for name, experiment in config["experiments"].items():
            variants = {}
            for variant, variant_config in experiment["variants"].items():
                assigned_sessions = {
                    row["session_id"] for row in assignments
                    if row["experiment_name"] == name and row["variant"] == variant
                }
                mode_filter = experiment.get("game_mode_filter")
                active_sessions = {
                    event["session_id"] for event in events
                    if event["session_id"] in assigned_sessions
                    and event["event_name"] == "game_started"
                    and (mode_filter is None or event["game_mode"] == mode_filter)
                    and (name != "adaptive_policy" or (
                        event["properties"].get("adaptive_difficulty") is True
                        and event["properties"].get("adaptive_policy") == variant_config["value"]
                    ))
                }
                subset = [event for event in events if event["session_id"] in active_sessions and (mode_filter is None or event["game_mode"] in {mode_filter, "none"})]
                starts = [event for event in subset if event["event_name"] == "round_started"]
                completes = [event for event in subset if event["event_name"] == "round_completed"]
                submitted = [event for event in subset if event["event_name"] == "drink_submitted"]
                order_events = [event for event in subset if event["event_name"] in {"drink_submitted", "order_failed"}]
                losses = [event for event in subset if event["event_name"] == "order_failed" and event["properties"].get("failure_type") == "lost"]
                hints = [event for event in subset if event["event_name"] == "hint_requested"]
                clarifications = [event for event in subset if event["event_name"] == "clarification_requested"]
                sessions_ended = [event for event in subset if event["event_name"] == "session_ended"]
                duration_values = [float(event["properties"].get("duration_seconds", 0)) for event in sessions_ended]
                variants[variant] = {
                    "label": variant_config["label"],
                    "sessions": len(active_sessions),
                    "assigned_sessions": len(assigned_sessions),
                    "completion_rate": round(len(completes) / len(starts), 3) if starts else 0,
                    "successful_orders_without_hints_rate": round(sum(bool(event["properties"].get("correct")) and int(event["properties"].get("hints_used", 0)) == 0 for event in submitted) / len(order_events), 3) if order_events else 0,
                    "customer_loss_rate": round(len(losses) / len(order_events), 3) if order_events else 0,
                    "average_score": self._average([float(event["properties"].get("score", 0)) for event in completes]),
                    "hint_usage_rate": round(sum(int(event["properties"].get("hints_used", 0)) > 0 for event in order_events) / len(order_events), 3) if order_events else 0,
                    "clarification_usage_rate": round(sum(int(event["properties"].get("clarifications_used", 0)) > 0 for event in order_events) / len(order_events), 3) if order_events else 0,
                    "average_response_time_seconds": self._average([
                        float(event["properties"].get("response_time_seconds", 0))
                        for event in order_events if "response_time_seconds" in event["properties"]
                    ]),
                    "average_session_duration_seconds": self._average(duration_values),
                }
            enough = all(variant["sessions"] >= config.get("minimum_exploratory_sessions_per_variant", MINIMUM_VARIANT_SESSIONS) for variant in variants.values())
            metric = experiment["primary_metric"]
            baseline = variants["A"][metric]
            comparison = variants["B"][metric]
            experiments[name] = {
                "hypothesis": experiment["hypothesis"],
                "primary_metric": metric,
                "guardrail_metric": experiment["guardrail_metric"],
                "guardrail_metrics": experiment.get("guardrail_metrics", [experiment["guardrail_metric"]]),
                "variants": variants,
                "primary_metric_delta": round(comparison - baseline, 3),
                "status": "exploratory" if not enough else "descriptive",
                "sample_warning": None if enough else "Insufficient data for strong conclusions.",
            }
        return {"experiments": experiments, "minimum_sessions_per_variant": config.get("minimum_exploratory_sessions_per_variant", MINIMUM_VARIANT_SESSIONS)}

    def export(self, output_format: str) -> tuple[str, str]:
        events = self.repository.load_events()
        if output_format == "json":
            return json.dumps(events, ensure_ascii=False, indent=2), "application/json"
        if output_format != "csv":
            raise AnalyticsValidationError("Export format must be csv or json.")
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=["event_name", "session_id", "player_id", "game_mode", "timestamp", "properties"])
        writer.writeheader()
        for event in events:
            writer.writerow({**event, "properties": json.dumps(event["properties"], ensure_ascii=False)})
        return stream.getvalue(), "text/csv"
