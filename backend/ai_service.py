from __future__ import annotations

import json
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Dict, List, Optional

import joblib

from schemas import EvaluationResponse, InterpretationResponse
from rule_parser import parse_keyword_order

MODEL_PATH = Path(__file__).resolve().parent / "model" / "order_parser.joblib"
LAB_MODELS_PATH = Path(__file__).resolve().parent / "model" / "ai_lab_models.joblib"
ROOT_PATH = Path(__file__).resolve().parents[1]
COMPARISON_REPORT_PATH = ROOT_PATH / "results" / "model_comparison.json"
ROBUSTNESS_DATA_PATH = ROOT_PATH / "data" / "robustness_eval.json"
LABELS = ["base", "milk", "sweetness", "topping", "vibe"]
LAB_MODEL_NAMES = ["keyword_rules", "multinomial_nb", "logistic_regression", "linear_svm"]


class BrewAIService:
    def __init__(self) -> None:
        self.model_bundle = None
        self.model_loaded = False
        self.model_load_error = None
        self.lab_models = None
        self.lab_model_metadata = None
        self.lab_model_errors = {}
        self.lab_models_initialized = False

        if MODEL_PATH.exists():
            try:
                bundle = joblib.load(MODEL_PATH)
                metadata = bundle.get("training_metadata", {})
                dataset_hash = hashlib.sha256((ROOT_PATH / "data" / "order_dataset.json").read_bytes()).hexdigest()
                if metadata.get("dataset_sha256") != dataset_hash:
                    raise ValueError("Production model provenance is missing or its dataset hash is stale.")
                if not all(label in bundle.get("models", {}) for label in LABELS):
                    raise ValueError("Production model artifact is missing an attribute classifier.")
                self.model_bundle = bundle
                self.model_loaded = True
            except Exception as error:
                self.model_load_error = str(error)

    def interpret_order(
        self,
        customer_name: str,
        request: str,
        persona_metadata: Optional[Dict] = None,
    ) -> InterpretationResponse:
        persona_fields = persona_metadata or {}
        if self.model_loaded:
            recipe, confidence = self._predict_with_model(request)
            explanation = [
                f"Parsed request for {customer_name}",
                "Prediction produced by trained baseline classifier",
            ]
            return InterpretationResponse(
                recipe=recipe,
                confidence=confidence,
                source="trained-baseline",
                explanation=explanation,
                **persona_fields,
            )

        recipe = parse_keyword_order(request)
        explanation = [
            f"Parsed request for {customer_name}",
            "No trained model found, so heuristic backup rules were used",
        ]
        return InterpretationResponse(
            recipe=recipe,
            confidence={label: None for label in LABELS},
            source="heuristic-backup",
            explanation=explanation,
            **persona_fields,
        )

    def evaluate_order(
        self,
        ground_truth_recipe: Dict[str, str],
        predicted_recipe: Dict[str, str],
        submitted_recipe: Dict[str, str],
    ) -> EvaluationResponse:
        ai_matches = sum(
            1
            for key in LABELS
            if predicted_recipe.get(key) == ground_truth_recipe.get(key)
        )
        total = len(LABELS)
        player_matches = sum(
            1
            for key in LABELS
            if submitted_recipe.get(key) == ground_truth_recipe.get(key)
        )

        if player_matches == total:
            feedback = (
                "<span class=\"success\">Perfect service.</span> "
                f"Your drink matched all {total} customer requirements. "
                f"The AI matched {ai_matches}/{total}."
            )
            return EvaluationResponse(
                ai_matches=ai_matches,
                player_matches=player_matches,
                total_attributes=total,
                points_awarded=120,
                combo_delta=1,
                feedback=feedback,
            )

        if player_matches >= 3:
            feedback = (
                f"Solid service. Your drink matched {player_matches}/{total} "
                f"customer requirements. The AI matched {ai_matches}/{total}."
            )
            return EvaluationResponse(
                ai_matches=ai_matches,
                player_matches=player_matches,
                total_attributes=total,
                points_awarded=75,
                combo_delta=1,
                feedback=feedback,
            )

        feedback = (
                "<span class=\"warning\">The customer may be disappointed.</span> "
                f"Your drink matched {player_matches}/{total} requirements. "
                f"The AI matched {ai_matches}/{total}."
        )
        return EvaluationResponse(
                ai_matches=ai_matches,
                player_matches=player_matches,
            total_attributes=total,
            points_awarded=30,
            combo_delta=0,
            feedback=feedback,
        )

    def _predict_with_model(
        self, request: str
    ) -> tuple[Dict[str, str], Dict[str, Optional[float]]]:
        recipe: Dict[str, str] = {}
        confidences: Dict[str, Optional[float]] = {}

        for label in LABELS:
            model = self.model_bundle["models"][label]
            prediction = model.predict([request])[0]
            probability_vector = model.predict_proba([request])[0]
            recipe[label] = str(prediction)
            confidences[label] = float(max(probability_vector))

        return recipe, confidences

    def _ensure_lab_models(self) -> None:
        if self.lab_models_initialized:
            return
        self.lab_models_initialized = True

        if LAB_MODELS_PATH.exists():
            try:
                cached = joblib.load(LAB_MODELS_PATH)
                cached_metadata = cached.get("metadata") or {}
                current_hash = hashlib.sha256((ROOT_PATH / "data" / "order_dataset.json").read_bytes()).hexdigest()
                if cached_metadata.get("artifact_version") == 1 and cached_metadata.get("dataset_sha256") == current_hash:
                    self.lab_models = cached.get("models", {})
                    self.lab_model_errors = cached.get("errors", {})
                    self.lab_model_metadata = cached_metadata
                    return
                self.lab_model_errors["cache"] = "Cached AI Lab models are stale; rebuilding from the current canonical dataset."
            except Exception as error:
                self.lab_model_errors["cache"] = f"Could not load the AI Lab model cache: {error}"

        try:
            if str(ROOT_PATH) not in sys.path:
                sys.path.insert(0, str(ROOT_PATH))
            from ml.compare_models import fit_comparison_models, load_dataset

            records = load_dataset()
            self.lab_models, training_errors = fit_comparison_models(records)
            self.lab_model_errors.update(training_errors)
            dataset_digest = hashlib.sha256(
                (ROOT_PATH / "data" / "order_dataset.json").read_bytes()
            ).hexdigest()
            self.lab_model_metadata = {
                "artifact_version": 1,
                "trained_at_utc": datetime.now(timezone.utc).isoformat(),
                "models": ["keyword_rules", "multinomial_nb", "logistic_regression", "linear_svm"],
                "training_examples": len(records),
                "dataset_sha256": dataset_digest,
                "training_scope": "All canonical labeled records for interactive AI Lab comparison; not an evaluation run.",
                "evaluation_reference": "results/model_comparison.json (separate grouped holdout and challenge-set evaluation)",
            }
            try:
                LAB_MODELS_PATH.parent.mkdir(parents=True, exist_ok=True)
                joblib.dump(
                    {"artifact_version": 1, "models": self.lab_models, "errors": self.lab_model_errors,
                     "metadata": self.lab_model_metadata},
                    LAB_MODELS_PATH,
                )
            except Exception as error:
                self.lab_model_errors["cache_write"] = f"Could not save the AI Lab model cache: {error}"
        except Exception as error:
            self.lab_models = {}
            self.lab_model_errors.update({name: f"Model setup failed: {error}" for name in LAB_MODEL_NAMES})

    def compare_lab_request(self, text: str, ground_truth: Optional[Dict[str, str]] = None) -> dict:
        if not text or not text.strip():
            raise ValueError("Enter a customer request before analyzing.")
        self._ensure_lab_models()
        model_results = {}

        for model_name in LAB_MODEL_NAMES:
            entry = (self.lab_models or {}).get(model_name)
            if entry is None:
                model_results[model_name] = {
                    "prediction": None,
                    "confidence": None,
                    "latency_ms": None,
                    "available": False,
                    "error": self.lab_model_errors.get(model_name, "Model artifact is unavailable."),
                }
                continue

            try:
                started = perf_counter()
                if entry["kind"] == "rules":
                    prediction = entry["model"].predict([text])[0]
                    confidence = None
                else:
                    prediction = {}
                    confidence_by_label = {}
                    has_confidence = True
                    for label in LABELS:
                        estimator = entry["models"][label]
                        prediction[label] = str(estimator.predict([text])[0])
                        if hasattr(estimator, "predict_proba"):
                            confidence_by_label[label] = float(max(estimator.predict_proba([text])[0]))
                        else:
                            has_confidence = False
                    confidence = confidence_by_label if has_confidence else None
                latency_ms = max(0.0, (perf_counter() - started) * 1000)
                model_results[model_name] = {
                    "prediction": prediction,
                    "confidence": confidence,
                    "latency_ms": latency_ms,
                    "available": True,
                    "error": None,
                }
            except Exception as error:
                model_results[model_name] = {
                    "prediction": None,
                    "confidence": None,
                    "latency_ms": None,
                    "available": False,
                    "error": str(error),
                }

        return {
            "models": model_results,
            "ground_truth": ground_truth,
        }

    @staticmethod
    def load_lab_summary() -> dict:
        served_model = "Calibrated TF-IDF + Logistic Regression (production baseline)"
        production_metadata_path = ROOT_PATH / "results" / "production_model_metadata.json"
        production_metadata = None
        try:
            production_metadata = json.loads(production_metadata_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        comparison_metadata = None
        if LAB_MODELS_PATH.exists():
            try:
                candidate_metadata = joblib.load(LAB_MODELS_PATH).get("metadata")
                current_hash = hashlib.sha256((ROOT_PATH / "data" / "order_dataset.json").read_bytes()).hexdigest()
                if candidate_metadata and candidate_metadata.get("dataset_sha256") == current_hash:
                    comparison_metadata = candidate_metadata
            except Exception:
                comparison_metadata = None
        if not COMPARISON_REPORT_PATH.exists():
            return {
                "benchmark_available": False,
                "benchmark_winner": None,
                "benchmark_macro_f1": None,
                "benchmark_average_latency_ms": None,
                "currently_served_model": served_model,
                "currently_served_source": "trained-baseline" if MODEL_PATH.exists() else "heuristic-backup",
                "production_macro_f1": production_metadata.get("macro_f1") if production_metadata else None,
                "production_evaluation": production_metadata.get("evaluation_method") if production_metadata else None,
                "production_reason": (production_metadata.get("benchmark_context") or {}).get("reason") if production_metadata else None,
                "comparison_model_metadata": comparison_metadata,
                "error": "The model comparison report is not available.",
            }
        try:
            with COMPARISON_REPORT_PATH.open("r", encoding="utf-8") as handle:
                report = json.load(handle)
            winner = report["summary"]["selected_best_model"]
            winner_result = report["models"][winner]["summary"]
            return {
                "benchmark_available": True,
                "benchmark_winner": winner,
                "benchmark_macro_f1": winner_result["average_macro_f1"],
                "benchmark_average_latency_ms": winner_result["mean_inference_latency_ms_per_order"],
                "currently_served_model": served_model,
                "currently_served_source": "trained-baseline" if MODEL_PATH.exists() else "heuristic-backup",
                "production_macro_f1": production_metadata.get("macro_f1") if production_metadata else None,
                "production_evaluation": production_metadata.get("evaluation_method") if production_metadata else None,
                "production_reason": (production_metadata.get("benchmark_context") or {}).get("reason") if production_metadata else None,
                "comparison_model_metadata": comparison_metadata,
                "error": None,
            }
        except Exception as error:
            return {
                "benchmark_available": False,
                "benchmark_winner": None,
                "benchmark_macro_f1": None,
                "benchmark_average_latency_ms": None,
                "currently_served_model": served_model,
                "currently_served_source": "trained-baseline" if MODEL_PATH.exists() else "heuristic-backup",
                "production_macro_f1": production_metadata.get("macro_f1") if production_metadata else None,
                "production_evaluation": production_metadata.get("evaluation_method") if production_metadata else None,
                "production_reason": (production_metadata.get("benchmark_context") or {}).get("reason") if production_metadata else None,
                "comparison_model_metadata": comparison_metadata,
                "error": f"Could not read the model comparison report: {error}",
            }

    @staticmethod
    def load_lab_examples() -> dict:
        with ROBUSTNESS_DATA_PATH.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        records = data.get("records", [])
        return {
            "categories": sorted({record["category"] for record in records}),
            "records": records,
        }

