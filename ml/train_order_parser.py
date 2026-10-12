from __future__ import annotations

import json
from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "order_dataset.json"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "backend" / "model" / "order_parser.joblib"
RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
LABELS = ["base", "milk", "sweetness", "topping", "vibe"]


def load_dataset() -> list[dict]:
    with DATA_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_confusion_matrix(y_true: list[str], y_pred: list[str], classes: list[str]) -> dict:
    matrix = confusion_matrix(y_true, y_pred, labels=classes)
    return {
        "labels": classes,
        "matrix": matrix.tolist(),
    }


def train_models(records: list[dict]) -> tuple[dict, dict]:
    texts = [record["utterance"] for record in records]
    bundle = {"labels": LABELS, "models": {}, "metrics": {}}
    results = {
        "dataset": {
            "path": DATA_PATH.relative_to(DATA_PATH.parents[1]).as_posix(),
            "record_count": len(records),
            "test_size": 0.25,
            "random_state": 42,
        },
        "models": {},
        "summary": {},
    }

    for label in LABELS:
        targets = [record[label] for record in records]
        class_labels = sorted(set(targets))
        x_train, x_test, y_train, y_test = train_test_split(
            texts,
            targets,
            test_size=0.25,
            random_state=42,
            stratify=targets,
        )

        pipeline = Pipeline(
            [
                ("tfidf", TfidfVectorizer(ngram_range=(1, 2), lowercase=True)),
                ("clf", LogisticRegression(max_iter=1000)),
            ]
        )
        calibrated_model = CalibratedClassifierCV(
            estimator=pipeline,
            method="sigmoid",
            cv=3,
        )
        calibrated_model.fit(x_train, y_train)

        predictions = calibrated_model.predict(x_test)
        accuracy = accuracy_score(y_test, predictions)
        report_dict = classification_report(y_test, predictions, zero_division=0, output_dict=True)
        report_text = classification_report(y_test, predictions, zero_division=0)
        matrix = build_confusion_matrix(y_test, predictions, class_labels)

        bundle["models"][label] = calibrated_model
        bundle["metrics"][label] = {"accuracy": accuracy, "report": report_text}
        results["models"][label] = {
            "accuracy": accuracy,
            "macro_precision": report_dict["macro avg"]["precision"],
            "macro_recall": report_dict["macro avg"]["recall"],
            "macro_f1": report_dict["macro avg"]["f1-score"],
            "weighted_f1": report_dict["weighted avg"]["f1-score"],
            "support": report_dict["macro avg"]["support"],
            "class_labels": class_labels,
            "classification_report": report_dict,
            "confusion_matrix": matrix,
        }

    accuracies = [results["models"][label]["accuracy"] for label in LABELS]
    macro_f1_scores = [results["models"][label]["macro_f1"] for label in LABELS]
    results["summary"] = {
        "average_accuracy": sum(accuracies) / len(accuracies),
        "average_macro_f1": sum(macro_f1_scores) / len(macro_f1_scores),
        "best_attribute_by_macro_f1": max(
            LABELS,
            key=lambda label_name: results["models"][label_name]["macro_f1"],
        ),
        "lowest_attribute_by_macro_f1": min(
            LABELS,
            key=lambda label_name: results["models"][label_name]["macro_f1"],
        ),
    }

    return bundle, results


def write_results(results: dict) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    metrics_path = RESULTS_DIR / "baseline_metrics.json"
    summary_path = RESULTS_DIR / "baseline_summary.md"

    metrics_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# Baseline Model Results",
        "",
        f"- Dataset: `{results['dataset']['path']}`",
        f"- Records: `{results['dataset']['record_count']}`",
        f"- Test split: `{results['dataset']['test_size']}`",
        f"- Random state: `{results['dataset']['random_state']}`",
        f"- Average accuracy: `{results['summary']['average_accuracy']:.3f}`",
        f"- Average macro F1: `{results['summary']['average_macro_f1']:.3f}`",
        f"- Best attribute: `{results['summary']['best_attribute_by_macro_f1']}`",
        f"- Lowest attribute: `{results['summary']['lowest_attribute_by_macro_f1']}`",
        "",
        "## Per-Attribute Results",
        "",
    ]

    for label in LABELS:
        metrics = results["models"][label]
        lines.extend(
            [
                f"### {label}",
                f"- Accuracy: `{metrics['accuracy']:.3f}`",
                f"- Macro precision: `{metrics['macro_precision']:.3f}`",
                f"- Macro recall: `{metrics['macro_recall']:.3f}`",
                f"- Macro F1: `{metrics['macro_f1']:.3f}`",
                f"- Weighted F1: `{metrics['weighted_f1']:.3f}`",
                "",
                "| Actual \\ Predicted | " + " | ".join(metrics["confusion_matrix"]["labels"]) + " |",
                "| --- | " + " | ".join(["---"] * len(metrics["confusion_matrix"]["labels"])) + " |",
            ]
        )

        for class_name, row in zip(
            metrics["confusion_matrix"]["labels"],
            metrics["confusion_matrix"]["matrix"],
        ):
            lines.append("| " + class_name + " | " + " | ".join(str(value) for value in row) + " |")

        lines.append("")

    summary_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    records = load_dataset()
    bundle, results = train_models(records)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, OUTPUT_PATH)
    write_results(results)

    print(f"Saved model bundle to: {OUTPUT_PATH}")
    print(f"Saved metrics to: {RESULTS_DIR / 'baseline_metrics.json'}")
    print(f"Saved summary to: {RESULTS_DIR / 'baseline_summary.md'}")
    for label, metrics in bundle["metrics"].items():
        print(f"\n[{label}] accuracy={metrics['accuracy']:.3f}")
        print(metrics["report"])


if __name__ == "__main__":
    main()
