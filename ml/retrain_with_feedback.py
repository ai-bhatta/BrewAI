from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

import joblib
import numpy as np
from sklearn.metrics import f1_score

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "backend"))
sys.path.insert(0, str(ROOT_DIR))

from feedback_repository import FeedbackRepository
from feedback_service import ATTRIBUTES, valid_labels
from ml.compare_models import (
    RESULTS_DIR,
    build_model_factories,
    grouped_holdout_split,
    load_dataset,
    load_robustness_dataset,
)

PRODUCTION_MODEL_PATH = ROOT_DIR / "backend" / "model" / "order_parser.joblib"
CANDIDATE_DIR = ROOT_DIR / "backend" / "model" / "candidates"
FEEDBACK_DB_PATH = ROOT_DIR / "data" / "feedback.sqlite3"
TRAINABLE_MODELS = ("multinomial_nb", "logistic_regression", "linear_svm")


def record_event(results_dir: Path, event: str) -> None:
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    with (results_dir / "feedback_events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"event": event, "timestamp": datetime.now(timezone.utc).isoformat()}) + "\n")


def normalize_text(text: str) -> str:
    return " ".join(text.casefold().split())


def validate_approved_examples(examples: list[dict], allowed: dict[str, set[str]]) -> tuple[list[dict], int]:
    valid = []
    rejected = 0
    for example in examples:
        if not isinstance(example, dict) or not isinstance(example.get("utterance"), str):
            rejected += 1
            continue
        if any(example.get(attribute) not in allowed[attribute] for attribute in ATTRIBUTES):
            rejected += 1
            continue
        valid.append(example)
    return valid, rejected


def score_model(model_bundle: dict, records: list[dict], class_labels: dict[str, list[str]]) -> dict:
    predictions = {attribute: [] for attribute in ATTRIBUTES}
    latency_ms = []
    for record in records:
        started = perf_counter()
        for attribute in ATTRIBUTES:
            predictions[attribute].append(str(model_bundle["models"][attribute].predict([record["utterance"]])[0]))
        latency_ms.append((perf_counter() - started) * 1000)
    per_attribute = {
        attribute: float(f1_score(
            [record[attribute] for record in records], predictions[attribute],
            labels=class_labels[attribute], average="macro", zero_division=0,
        ))
        for attribute in ATTRIBUTES
    }
    return {
        "per_attribute_macro_f1": per_attribute,
        "macro_f1": float(np.mean(list(per_attribute.values()))) if per_attribute else 0.0,
        "mean_latency_ms_per_order": float(np.mean(latency_ms)) if latency_ms else 0.0,
        "example_count": len(records),
    }


def fit_candidate(model_name: str, train_records: list[dict]) -> dict:
    if model_name not in TRAINABLE_MODELS:
        raise ValueError(f"Choose a trainable candidate: {', '.join(TRAINABLE_MODELS)}")
    factory = build_model_factories()[model_name]
    texts = [record["utterance"] for record in train_records]
    estimators = {}
    for attribute in ATTRIBUTES:
        estimator = factory()
        estimator.fit(texts, [record[attribute] for record in train_records])
        estimators[attribute] = estimator
    return {"labels": list(ATTRIBUTES), "models": estimators, "model_name": model_name}


def compare_evaluations(baseline: dict, candidate: dict) -> tuple[list[dict], list[dict]]:
    regressions = []
    improvements = []
    for section in ("grouped_holdout", "challenge_set"):
        before = baseline[section]["per_attribute_macro_f1"]
        after = candidate[section]["per_attribute_macro_f1"]
        for attribute in ATTRIBUTES:
            difference = after[attribute] - before[attribute]
            item = {"evaluation": section, "attribute": attribute, "before": before[attribute], "after": after[attribute], "change": difference}
            if difference < -1e-9:
                regressions.append(item)
            elif difference > 1e-9:
                improvements.append(item)
        delta = candidate[section]["macro_f1"] - baseline[section]["macro_f1"]
        if delta < -1e-9:
            regressions.append({"evaluation": section, "attribute": "overall", "before": baseline[section]["macro_f1"], "after": candidate[section]["macro_f1"], "change": delta})
    return improvements, regressions


def evaluate_candidate(
    model_name: str = "logistic_regression",
    records: list[dict] | None = None,
    approved_examples: list[dict] | None = None,
    baseline_bundle: dict | None = None,
    robustness_records: list[dict] | None = None,
    candidate_dir: Path = CANDIDATE_DIR,
    results_dir: Path = RESULTS_DIR,
) -> dict:
    """Train and evaluate without modifying either source data or production artifacts."""
    original_records = records if records is not None else load_dataset()
    if not approved_examples:
        raise ValueError("No approved feedback examples are available for training.")
    if baseline_bundle is None:
        if not PRODUCTION_MODEL_PATH.exists():
            raise FileNotFoundError(f"Production baseline model is missing: {PRODUCTION_MODEL_PATH}")
        baseline_bundle = joblib.load(PRODUCTION_MODEL_PATH)

    allowed = {attribute: sorted({record[attribute] for record in original_records}) for attribute in ATTRIBUTES}
    valid_feedback, invalid_feedback_count = validate_approved_examples(
        approved_examples, {attribute: set(values) for attribute, values in allowed.items()}
    )
    if not valid_feedback:
        raise ValueError("No valid approved feedback examples remain after validation.")

    train_indices, test_indices, split_metadata = grouped_holdout_split(original_records)
    training_records = [original_records[int(index)] for index in train_indices]
    test_records = [original_records[int(index)] for index in test_indices]
    holdout_texts = {normalize_text(record["utterance"]) for record in test_records}
    training_keys = {
        (normalize_text(record["utterance"]), tuple(record[attr] for attr in ATTRIBUTES))
        for record in training_records
    }
    accepted_feedback = []
    duplicate_feedback_count = 0
    holdout_feedback_count = 0
    for example in valid_feedback:
        normalized = normalize_text(example["utterance"])
        if normalized in holdout_texts:
            holdout_feedback_count += 1
            continue
        key = (normalized, tuple(example[attr] for attr in ATTRIBUTES))
        if key in training_keys:
            duplicate_feedback_count += 1
            continue
        training_keys.add(key)
        accepted_feedback.append(example)
    if not accepted_feedback:
        raise ValueError("Approved feedback contains no new examples after deduplication and holdout-leakage filtering.")

    combined_training = training_records + accepted_feedback
    results_dir = Path(results_dir)
    record_event(results_dir, "candidate_training_started")
    try:
        no_feedback_control = fit_candidate(model_name, training_records)
        candidate = fit_candidate(model_name, combined_training)
    except Exception:
        record_event(results_dir, "candidate_training_failed")
        raise
    record_event(results_dir, "candidate_training_completed")
    if robustness_records is None:
        robustness_records, _annotation_note = load_robustness_dataset()
    class_labels = {attribute: allowed[attribute] for attribute in ATTRIBUTES}
    try:
        baseline = {
            "grouped_holdout": score_model(baseline_bundle, test_records, class_labels),
            "challenge_set": score_model(baseline_bundle, robustness_records, class_labels),
        }
        candidate_scores = {
            "grouped_holdout": score_model(candidate, test_records, class_labels),
            "challenge_set": score_model(candidate, robustness_records, class_labels),
        }
        control_scores = {
            "grouped_holdout": score_model(no_feedback_control, test_records, class_labels),
            "challenge_set": score_model(no_feedback_control, robustness_records, class_labels),
        }
    except Exception:
        record_event(results_dir, "candidate_evaluation_failed")
        raise
    record_event(results_dir, "candidate_evaluated")

    improvements, regressions = compare_evaluations(baseline, candidate_scores)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    candidate_dir = Path(candidate_dir)
    candidate_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)
    candidate_path = candidate_dir / f"{model_name}_feedback_{timestamp}.joblib"
    report_path = results_dir / f"feedback_retrain_{timestamp}.json"
    markdown_path = results_dir / f"feedback_retrain_{timestamp}.md"
    candidate["training_metadata"] = {
        "artifact_version": 1,
        "model": model_name,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "original_training_examples": len(training_records),
        "canonical_dataset_sha256": hashlib.sha256((ROOT_DIR / "data" / "order_dataset.json").read_bytes()).hexdigest(),
        "feedback_examples_sha256": hashlib.sha256(json.dumps(
            [{key: item.get(key) for key in ("id", "utterance", *ATTRIBUTES)} for item in accepted_feedback],
            sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")).hexdigest(),
        "feedback_examples": len(accepted_feedback),
        "evaluation_method": "Same grouped holdout and fixed robustness challenge set; candidate trained from grouped training records plus approved, validated feedback only.",
        "grouped_holdout_macro_f1": candidate_scores["grouped_holdout"]["macro_f1"],
        "challenge_set_macro_f1": candidate_scores["challenge_set"]["macro_f1"],
    }
    candidate["artifact_version"] = 1
    joblib.dump(candidate, candidate_path)
    baseline_metadata = baseline_bundle.get("training_metadata") or {}
    baseline_is_clean = (
        baseline_metadata.get("dataset_sha256") == hashlib.sha256((ROOT_DIR / "data" / "order_dataset.json").read_bytes()).hexdigest()
        and baseline_metadata.get("training_examples") == len(training_records)
        and baseline_metadata.get("holdout_examples") == len(test_records)
    )
    report = {
        "model": model_name,
        "baseline": baseline,
        "no_feedback_control": control_scores,
        "candidate": candidate_scores,
        "feedback_examples": len(accepted_feedback),
        "feedback_ids": [example.get("id") for example in accepted_feedback],
        "invalid_feedback_examples": invalid_feedback_count,
        "duplicate_feedback_examples": duplicate_feedback_count,
        "holdout_feedback_excluded": holdout_feedback_count,
        "improvements": improvements,
        "regressions": regressions,
        "recommendation": "review",
        "events": ["candidate_training_started", "candidate_training_completed", "candidate_evaluated"],
        "candidate_artifact": str(candidate_path),
        "candidate_artifact_metadata": candidate["training_metadata"],
        "evaluation": {
            "method": "Same grouped holdout split and robustness challenge set for baseline and candidate.",
            "split": split_metadata,
            "baseline_note": "Production baseline was trained on the matching grouped training partition; this holdout was excluded from production fitting." if baseline_is_clean else "Baseline training membership could not be verified; baseline scores may include training-set leakage.",
            "original_dataset_modified": False,
            "production_model_modified": False,
        },
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "# Human Feedback Candidate Evaluation", "",
        f"- Candidate: `{model_name}`", f"- Approved feedback added: `{len(accepted_feedback)}`",
        f"- Grouped holdout macro F1: `{baseline['grouped_holdout']['macro_f1']:.3f}` -> `{candidate_scores['grouped_holdout']['macro_f1']:.3f}`",
        f"- Challenge-set macro F1: `{baseline['challenge_set']['macro_f1']:.3f}` -> `{candidate_scores['challenge_set']['macro_f1']:.3f}`",
        f"- Matched no-feedback control to candidate grouped holdout macro F1: `{control_scores['grouped_holdout']['macro_f1']:.3f}` -> `{candidate_scores['grouped_holdout']['macro_f1']:.3f}`",
        f"- Candidate latency/order: `{candidate_scores['grouped_holdout']['mean_latency_ms_per_order']:.3f} ms`",
        f"- Per-attribute regressions: `{len(regressions)}`", "- Recommendation: `review` (no automatic promotion)",
        "", "## Attribute F1 Changes", "", "| Evaluation | Attribute | Before | After | Change |", "| --- | --- | ---: | ---: | ---: |",
    ]
    for section in ("grouped_holdout", "challenge_set"):
        for attribute in ATTRIBUTES:
            before = baseline[section]["per_attribute_macro_f1"][attribute]
            after = candidate_scores[section]["per_attribute_macro_f1"][attribute]
            lines.append(f"| {section} | {attribute} | {before:.3f} | {after:.3f} | {after-before:+.3f} |")
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Train and evaluate a separate BrewAI candidate with reviewed feedback.")
    parser.add_argument("--model", choices=TRAINABLE_MODELS, default="logistic_regression")
    args = parser.parse_args()
    repository = FeedbackRepository(FEEDBACK_DB_PATH)
    approved = repository.approved_examples()
    if not approved:
        parser.error("No approved feedback examples are available. Review and approve corrections in AI Lab first.")
    try:
        result = evaluate_candidate(args.model, approved_examples=approved)
    except Exception as error:
        logging.exception("Candidate training/evaluation failed")
        parser.exit(status=1, message=f"Candidate was not promoted: {error}\n")
    print(f"Candidate saved: {result['candidate_artifact']}")
    print(f"Evaluation report: {RESULTS_DIR}")
    print(f"Review recommendation; regressions detected: {len(result['regressions'])}")


if __name__ == "__main__":
    main()
