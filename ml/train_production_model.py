from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from sklearn.pipeline import Pipeline

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ml.compare_models import grouped_holdout_split, load_dataset

DATASET_PATH = ROOT / "data" / "order_dataset.json"
MODEL_PATH = ROOT / "backend" / "model" / "order_parser.joblib"
METADATA_PATH = ROOT / "results" / "production_model_metadata.json"
ATTRIBUTES = ("base", "milk", "sweetness", "topping", "vibe")
RANDOM_SEED = 42
PRODUCTION_MODEL_NAME = "calibrated_logistic_regression"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_estimator():
    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), lowercase=True)),
        ("clf", LogisticRegression(max_iter=1000, random_state=RANDOM_SEED)),
    ])
    return CalibratedClassifierCV(estimator=pipeline, method="sigmoid", cv=3)


def train_production_model() -> dict:
    records = load_dataset(DATASET_PATH)
    train_indices, test_indices, split = grouped_holdout_split(records)
    training = [records[int(index)] for index in train_indices]
    holdout = [records[int(index)] for index in test_indices]
    texts = [record["utterance"] for record in training]
    models = {}
    per_attribute = {}
    for attribute in ATTRIBUTES:
        estimator = build_estimator()
        estimator.fit(texts, [record[attribute] for record in training])
        models[attribute] = estimator
        expected = [record[attribute] for record in holdout]
        predicted = estimator.predict([record["utterance"] for record in holdout])
        per_attribute[attribute] = float(f1_score(expected, predicted, average="macro", zero_division=0))

    metadata = {
        "artifact_version": 1,
        "model": PRODUCTION_MODEL_NAME,
        "algorithm": "CalibratedClassifierCV(sigmoid) over word unigram/bigram TF-IDF + LogisticRegression",
        "training_examples": len(training),
        "holdout_examples": len(holdout),
        "canonical_dataset": "data/order_dataset.json",
        "dataset_examples": len(records),
        "dataset_sha256": sha256_file(DATASET_PATH),
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "random_seed": RANDOM_SEED,
        "evaluation_method": "StratifiedGroupKFold grouped by base label and connected character n-gram similarity clusters; deterministic first fold; holdout excluded from artifact fitting",
        "split": split,
        "per_attribute_macro_f1": per_attribute,
        "macro_f1": float(np.mean(list(per_attribute.values()))),
        "metric_scope": "Grouped holdout only; not the robustness/challenge set and not a claim of general accuracy.",
        "benchmark_context": {
            "benchmark_winner": "linear_svm",
            "benchmark_metric": "0.977 macro F1 in results/model_comparison.json grouped holdout; separate comparison experiment",
            "production_model": PRODUCTION_MODEL_NAME,
            "reason": "Retain the existing probability-producing calibrated Logistic Regression production baseline; the Linear SVM comparison candidate does not expose calibrated probabilities, which the gameplay confidence UI consumes. This clean run does not automatically promote a different model.",
        },
    }
    bundle = {
        "artifact_version": 1,
        "model_name": PRODUCTION_MODEL_NAME,
        "labels": list(ATTRIBUTES),
        "models": models,
        "training_metadata": metadata,
    }
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, MODEL_PATH)
    METADATA_PATH.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata


if __name__ == "__main__":
    result = train_production_model()
    print(json.dumps(result, indent=2))
