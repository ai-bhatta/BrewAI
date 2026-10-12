from __future__ import annotations

import json
import sys
from pathlib import Path
from time import perf_counter
from typing import Callable

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT_DIR / "data" / "order_dataset.json"
ROBUSTNESS_PATH = ROOT_DIR / "data" / "robustness_eval.json"
RESULTS_DIR = ROOT_DIR / "results"
LABELS = ["base", "milk", "sweetness", "topping", "vibe"]
TEST_SIZE = 0.25
RANDOM_STATE = 42
SIMILARITY_THRESHOLD = 0.55
BACKEND_DIR = ROOT_DIR / "backend"
sys.path.insert(0, str(BACKEND_DIR))
from rule_parser import parse_keyword_order


class KeywordRuleModel:
    def predict(self, texts: list[str]) -> list[dict[str, str]]:
        return [parse_keyword_order(text) for text in texts]


def load_dataset(path: Path = DATA_PATH) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_robustness_dataset() -> tuple[list[dict], str]:
    with ROBUSTNESS_PATH.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data["records"], data["annotation_note"]


def build_model_factories() -> dict[str, Callable[[], object]]:
    return {
        "keyword_rules": KeywordRuleModel,
        "multinomial_nb": lambda: Pipeline(
            [
                ("tfidf", TfidfVectorizer(ngram_range=(1, 2), lowercase=True)),
                ("clf", MultinomialNB()),
            ]
        ),
        "logistic_regression": lambda: Pipeline(
            [
                ("tfidf", TfidfVectorizer(ngram_range=(1, 2), lowercase=True)),
                ("clf", LogisticRegression(max_iter=1000)),
            ]
        ),
        "linear_svm": lambda: Pipeline(
            [
                ("tfidf", TfidfVectorizer(ngram_range=(1, 2), lowercase=True)),
                ("clf", LinearSVC()),
            ]
        ),
    }


def fit_comparison_models(records: list[dict]) -> tuple[dict[str, dict], dict[str, str]]:
    """Fit reusable AI Lab candidates once, independently of holdout evaluation."""
    factories = build_model_factories()
    texts = [record["utterance"] for record in records]
    models: dict[str, dict] = {}
    errors: dict[str, str] = {}
    for model_name, factory in factories.items():
        try:
            if model_name == "keyword_rules":
                models[model_name] = {"kind": "rules", "model": factory()}
                continue
            estimators = {}
            for label in LABELS:
                estimator = factory()
                estimator.fit(texts, [record[label] for record in records])
                estimators[label] = estimator
            models[model_name] = {"kind": "classifiers", "models": estimators}
        except Exception as error:
            errors[model_name] = str(error)
    return models, errors


def grouped_holdout_split(records: list[dict]) -> tuple[np.ndarray, np.ndarray, dict]:
    texts = [record["utterance"] for record in records]
    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5))
    text_vectors = vectorizer.fit_transform([text.lower() for text in texts])
    similarity = (text_vectors @ text_vectors.T).toarray()
    groups = np.full(len(records), -1, dtype=int)
    group_count = 0
    for seed in range(len(records)):
        if groups[seed] != -1:
            continue
        groups[seed] = group_count
        stack = [seed]
        while stack:
            current = stack.pop()
            neighbors = np.flatnonzero(similarity[current] >= SIMILARITY_THRESHOLD)
            for neighbor in neighbors:
                if groups[neighbor] == -1:
                    groups[neighbor] = group_count
                    stack.append(int(neighbor))
        group_count += 1

    splitter = StratifiedGroupKFold(
        n_splits=round(1 / TEST_SIZE),
        shuffle=True,
        random_state=RANDOM_STATE,
    )
    train_indices, test_indices = next(
        splitter.split(texts, [record["base"] for record in records], groups)
    )
    max_cross_similarity = float(
        similarity[np.ix_(train_indices, test_indices)].max()
    )
    metadata = {
        "method": "StratifiedGroupKFold by base label; character n-gram similarity groups",
        "test_size_target": TEST_SIZE,
        "test_size_actual": len(test_indices) / len(records),
        "random_state": RANDOM_STATE,
        "similarity_threshold": SIMILARITY_THRESHOLD,
        "template_group_count": int(group_count),
        "train_count": len(train_indices),
        "test_count": len(test_indices),
        "max_train_test_similarity": max_cross_similarity,
    }
    return train_indices, test_indices, metadata


def summarize_predictions(
    records: list[dict],
    predictions: dict[str, list[str]],
    latency_by_order_ms: list[float],
    class_labels_by_attribute: dict[str, list[str]],
) -> dict:
    attributes = {}
    for label in LABELS:
        expected = [record[label] for record in records]
        actual = predictions[label]
        class_labels = class_labels_by_attribute[label]
        report = classification_report(
            expected,
            actual,
            labels=class_labels,
            zero_division=0,
            output_dict=True,
        )
        attributes[label] = {
            "accuracy": accuracy_score(expected, actual),
            "macro_precision": report["macro avg"]["precision"],
            "macro_recall": report["macro avg"]["recall"],
            "macro_f1": report["macro avg"]["f1-score"],
            "weighted_f1": report["weighted avg"]["f1-score"],
            "support": len(expected),
            "class_labels": class_labels,
            "confusion_matrix": {
                "labels": class_labels,
                "matrix": confusion_matrix(expected, actual, labels=class_labels).tolist(),
            },
        }

    attribute_metrics = list(attributes.values())
    return {
        "attributes": attributes,
        "summary": {
            "example_count": len(records),
            "average_accuracy": float(np.mean([metric["accuracy"] for metric in attribute_metrics])),
            "average_macro_f1": float(np.mean([metric["macro_f1"] for metric in attribute_metrics])),
            "mean_inference_latency_ms_per_order": float(np.mean(latency_by_order_ms)),
            "p95_inference_latency_ms_per_order": float(np.percentile(latency_by_order_ms, 95)),
        },
    }


def train_and_evaluate(
    records: list[dict],
    train_indices: np.ndarray,
    test_records: list[dict],
    factories: dict[str, Callable[[], object]],
    class_labels_by_attribute: dict[str, list[str]],
) -> dict[str, dict]:
    results = {}
    train_texts = [records[index]["utterance"] for index in train_indices]
    train_records = [records[index] for index in train_indices]
    test_texts = [record["utterance"] for record in test_records]

    for model_name, factory in factories.items():
        estimators = {}
        if model_name == "keyword_rules":
            rule_model = factory()
            estimators = {label: rule_model for label in LABELS}
        else:
            for label in LABELS:
                estimator = factory()
                estimator.fit(train_texts, [record[label] for record in train_records])
                estimators[label] = estimator

        predictions = {label: [] for label in LABELS}
        latency_by_order_ms = []
        for text in test_texts:
            started = perf_counter()
            for label in LABELS:
                prediction = estimators[label].predict([text])[0]
                if model_name == "keyword_rules":
                    prediction = prediction[label]
                predictions[label].append(str(prediction))
            latency_by_order_ms.append((perf_counter() - started) * 1000)

        results[model_name] = summarize_predictions(
            test_records,
            predictions,
            latency_by_order_ms,
            class_labels_by_attribute,
        )
    return results


def evaluate_models(records: list[dict], robustness_records: list[dict], annotation_note: str) -> dict:
    train_indices, test_indices, split_metadata = grouped_holdout_split(records)
    test_records = [records[index] for index in test_indices]
    factories = build_model_factories()
    class_labels = {
        label: sorted({record[label] for record in records})
        for label in LABELS
    }
    holdout_results = train_and_evaluate(
        records,
        train_indices,
        test_records,
        factories,
        class_labels,
    )

    categories = sorted({record["category"] for record in robustness_records})
    results = {
        "dataset": {
            "path": DATA_PATH.relative_to(ROOT_DIR).as_posix(),
            "record_count": len(records),
            "split": split_metadata,
            "robustness_examples": len(robustness_records),
            "robustness_annotation_note": annotation_note,
            "robustness_categories": categories,
        },
        "models": {},
        "summary": {},
    }

    for model_name, holdout in holdout_results.items():
        results["models"][model_name] = {
            **holdout,
            "categories": {},
        }

    for category in categories:
        category_records = [
            record for record in robustness_records if record["category"] == category
        ]
        category_results = train_and_evaluate(
            records,
            train_indices,
            category_records,
            factories,
            class_labels,
        )
        for model_name, category_result in category_results.items():
            results["models"][model_name]["categories"][category] = category_result

    best_model = max(
        results["models"],
        key=lambda name: results["models"][name]["summary"]["average_macro_f1"],
    )
    results["summary"] = {
        "candidate_models": list(factories),
        "selected_best_model": best_model,
        "selected_best_model_macro_f1": results["models"][best_model]["summary"]["average_macro_f1"],
    }
    return results


def write_results(results: dict) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = RESULTS_DIR / "model_comparison.json"
    md_path = RESULTS_DIR / "model_comparison.md"
    json_path.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    split = results["dataset"]["split"]
    lines = [
        "# Model Comparison Results",
        "",
        f"- Dataset records: `{results['dataset']['record_count']}`",
        f"- Split: `{split['method']}`",
        f"- Train/test: `{split['train_count']}/{split['test_count']}`",
        f"- Similarity threshold: `{split['similarity_threshold']}`",
        f"- Maximum train/test similarity: `{split['max_train_test_similarity']:.3f}`",
        f"- Robustness examples: `{results['dataset']['robustness_examples']}`",
        f"- Best grouped-holdout model: `{results['summary']['selected_best_model']}`",
        "",
        "## Grouped Holdout Comparison",
        "",
        "| Model | Avg Accuracy | Avg Macro F1 | Mean Latency / Order (ms) | P95 Latency / Order (ms) |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for name, model_result in results["models"].items():
        summary = model_result["summary"]
        lines.append(
            f"| {name} | {summary['average_accuracy']:.3f} | {summary['average_macro_f1']:.3f} "
            f"| {summary['mean_inference_latency_ms_per_order']:.3f} "
            f"| {summary['p95_inference_latency_ms_per_order']:.3f} |"
        )

    lines.extend([
        "",
        "## Per-Attribute Macro F1",
        "",
        "| Attribute | " + " | ".join(results["models"]) + " |",
        "| --- | " + " | ".join(["---:"] * len(results["models"])) + " |",
    ])
    for label in LABELS:
        values = [f"{results['models'][name]['attributes'][label]['macro_f1']:.3f}" for name in results["models"]]
        lines.append(f"| {label} | " + " | ".join(values) + " |")

    lines.extend(["", "## Robustness Categories", "", "| Category | " + " | ".join(results["models"]) + " |", "| --- | " + " | ".join(["---:"] * len(results["models"])) + " |"])
    for category in results["dataset"]["robustness_categories"]:
        values = [
            f"{results['models'][name]['categories'][category]['summary']['average_macro_f1']:.3f}"
            for name in results["models"]
        ]
        lines.append(f"| {category} | " + " | ".join(values) + " |")

    lines.extend([
        "",
        "Confusion matrices, per-class precision/recall/F1, per-category attribute metrics, and latency details are in `model_comparison.json`.",
        results["dataset"]["robustness_annotation_note"],
        "",
    ])
    md_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    records = load_dataset()
    robustness_records, annotation_note = load_robustness_dataset()
    results = evaluate_models(records, robustness_records, annotation_note)
    write_results(results)
    summary = results["summary"]
    print(f"Saved comparison JSON to: {RESULTS_DIR / 'model_comparison.json'}")
    print(f"Saved comparison summary to: {RESULTS_DIR / 'model_comparison.md'}")
    print(
        f"Best grouped-holdout model: {summary['selected_best_model']} "
        f"(macro F1={summary['selected_best_model_macro_f1']:.3f})"
    )


if __name__ == "__main__":
    main()
