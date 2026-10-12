from __future__ import annotations

import json
from pathlib import Path

from feedback_repository import DuplicateFeedbackError, FeedbackRepository

ROOT_PATH = Path(__file__).resolve().parents[1]
DATABASE_PATH = ROOT_PATH / "data" / "feedback.sqlite3"
DATASET_PATH = ROOT_PATH / "data" / "order_dataset.json"
ATTRIBUTES = ("base", "milk", "sweetness", "topping", "vibe")
MODEL_NAMES = {"keyword_rules", "multinomial_nb", "logistic_regression", "linear_svm"}
LOW_CONFIDENCE_THRESHOLD = 0.5


class FeedbackValidationError(ValueError):
    pass


def valid_labels() -> dict[str, set[str]]:
    with DATASET_PATH.open("r", encoding="utf-8") as handle:
        records = json.load(handle)
    return {attribute: {record[attribute] for record in records} for attribute in ATTRIBUTES}


class FeedbackService:
    def __init__(self, repository: FeedbackRepository | None = None) -> None:
        self.repository = repository or FeedbackRepository(DATABASE_PATH)

    def submit(self, payload: dict) -> dict:
        text = payload.get("text")
        model = payload.get("model")
        if not isinstance(text, str) or not text.strip() or len(text) > 1000:
            raise FeedbackValidationError("Request text must contain 1-1000 characters.")
        if model not in MODEL_NAMES:
            raise FeedbackValidationError("Unknown model name.")
        expected_keys = set(ATTRIBUTES)
        predicted = payload.get("predicted")
        corrected = payload.get("corrected")
        if not isinstance(predicted, dict) or set(predicted) != expected_keys:
            raise FeedbackValidationError("A complete model prediction is required.")
        if not isinstance(corrected, dict) or set(corrected) != expected_keys:
            raise FeedbackValidationError("Provide a corrected value for every recipe attribute.")
        allowed = valid_labels()
        for recipe_name, recipe in (("predicted", predicted), ("corrected", corrected)):
            for attribute in ATTRIBUTES:
                if not isinstance(recipe[attribute], str) or recipe[attribute] not in allowed[attribute]:
                    raise FeedbackValidationError(f"Invalid {attribute} value in {recipe_name} recipe.")
        if predicted == corrected:
            raise FeedbackValidationError("The correction must change at least one predicted attribute.")
        confidence = payload.get("confidence")
        if confidence is not None:
            if not isinstance(confidence, dict) or set(confidence) - expected_keys:
                raise FeedbackValidationError("Confidence must contain known recipe attributes.")
            for value in confidence.values():
                if value is not None and (not isinstance(value, (int, float)) or not 0 <= value <= 1):
                    raise FeedbackValidationError("Confidence values must be between 0 and 1 or null.")
        low_confidence = bool(confidence) and any(
            value is not None and value < LOW_CONFIDENCE_THRESHOLD for value in confidence.values()
        )
        disagreement = bool(payload.get("model_disagreement", False))
        entry = {
            "text": text.strip(), "model": model, "predicted": predicted,
            "corrected": corrected, "confidence": confidence,
            "model_disagreement": disagreement, "low_confidence": low_confidence,
            "priority": 1 if disagreement else 2 if low_confidence else 3,
        }
        try:
            saved, similar = self.repository.create(entry)
        except DuplicateFeedbackError:
            raise
        return {"feedback": saved, "similar_entries": similar}

    def list_entries(self, status: str | None = "pending") -> list[dict]:
        if status not in (None, "pending", "approved", "rejected", "used_for_training"):
            raise FeedbackValidationError("Invalid feedback status filter.")
        return self.repository.list_entries(status)

    def review(self, feedback_id: str, decision: str) -> dict | None:
        if decision not in ("approved", "rejected"):
            raise FeedbackValidationError("Review decision must be approved or rejected.")
        return self.repository.review(feedback_id, decision)
