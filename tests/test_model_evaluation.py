import unittest

from ml.compare_models import (
    LABELS,
    grouped_holdout_split,
    load_dataset,
    load_robustness_dataset,
    summarize_predictions,
)


class ModelEvaluationTests(unittest.TestCase):
    def test_similar_utterances_do_not_cross_grouped_holdout(self) -> None:
        records = load_dataset()
        train_indices, test_indices, metadata = grouped_holdout_split(records)

        self.assertGreater(len(train_indices), 0)
        self.assertGreater(len(test_indices), 0)
        self.assertLess(
            metadata["max_train_test_similarity"],
            metadata["similarity_threshold"],
        )

    def test_robustness_set_contains_all_planned_categories(self) -> None:
        records, _annotation_note = load_robustness_dataset()
        expected = {
            "normal",
            "paraphrase",
            "typo",
            "slang",
            "negation",
            "ambiguity",
            "out_of_distribution",
        }

        self.assertEqual({record["category"] for record in records}, expected)
        self.assertTrue(all(all(label in record for label in LABELS) for record in records))

    def test_summary_includes_metrics_confusion_matrices_and_latency(self) -> None:
        records = [
            {"base": "espresso", "milk": "oat milk", "sweetness": "light sugar", "topping": "boba", "vibe": "cozy"},
            {"base": "matcha", "milk": "none", "sweetness": "no sugar", "topping": "none", "vibe": "classic"},
        ]
        predictions = {label: [record[label] for record in records] for label in LABELS}
        classes = {
            label: sorted({record[label] for record in records})
            for label in LABELS
        }

        result = summarize_predictions(records, predictions, [1.0, 2.0], classes)

        self.assertIn("macro_precision", result["attributes"]["base"])
        self.assertIn("macro_recall", result["attributes"]["base"])
        self.assertIn("macro_f1", result["attributes"]["base"])
        self.assertIn("confusion_matrix", result["attributes"]["base"])
        self.assertEqual(result["summary"]["mean_inference_latency_ms_per_order"], 1.5)


if __name__ == "__main__":
    unittest.main()
