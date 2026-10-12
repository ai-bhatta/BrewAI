import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ai_service import BrewAIService, LAB_MODEL_NAMES
from ml.compare_models import fit_comparison_models, load_dataset


class AILabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.models, cls.training_errors = fit_comparison_models(load_dataset())
        cls.service = BrewAIService.__new__(BrewAIService)
        cls.service.lab_models = cls.models
        cls.service.lab_model_errors = cls.training_errors
        cls.service.lab_models_initialized = True

    def test_compares_same_free_form_request_across_candidates(self):
        result = self.service.compare_lab_request(
            "espresso with oat milk, light sugar, boba, cozy"
        )
        self.assertEqual(set(result["models"]), set(LAB_MODEL_NAMES))
        for model in result["models"].values():
            self.assertTrue(model["available"], model["error"])
            self.assertEqual(set(model["prediction"]), {"base", "milk", "sweetness", "topping", "vibe"})
            self.assertGreaterEqual(model["latency_ms"], 0)
        self.assertIsNone(result["ground_truth"])

    def test_confidence_is_optional_and_not_fabricated(self):
        result = self.service.compare_lab_request("matcha, no sugar")
        self.assertIsNone(result["models"]["keyword_rules"]["confidence"])
        self.assertIsNone(result["models"]["linear_svm"]["confidence"])
        self.assertIsInstance(result["models"]["multinomial_nb"]["confidence"], dict)
        self.assertIsInstance(result["models"]["logistic_regression"]["confidence"], dict)

    def test_model_failure_is_isolated(self):
        class BrokenRules:
            def predict(self, _texts):
                raise RuntimeError("deliberate test failure")

        original = self.service.lab_models["keyword_rules"]
        self.service.lab_models["keyword_rules"] = {"kind": "rules", "model": BrokenRules()}
        try:
            result = self.service.compare_lab_request("espresso")
        finally:
            self.service.lab_models["keyword_rules"] = original
        self.assertFalse(result["models"]["keyword_rules"]["available"])
        self.assertIn("deliberate test failure", result["models"]["keyword_rules"]["error"])
        self.assertTrue(result["models"]["logistic_regression"]["available"])

    def test_benchmark_report_distinguishes_winner_from_served_model(self):
        summary = BrewAIService.load_lab_summary()
        self.assertTrue(summary["benchmark_available"], summary["error"])
        self.assertEqual(summary["benchmark_winner"], "linear_svm")
        self.assertIn("Logistic Regression", summary["currently_served_model"])
        self.assertNotEqual(summary["benchmark_winner"], "logistic_regression")

    def test_robustness_records_are_labeled_and_categorized(self):
        examples = BrewAIService.load_lab_examples()
        self.assertTrue(examples["categories"])
        self.assertTrue(examples["records"])
        self.assertTrue(all("utterance" in record and "base" in record for record in examples["records"]))

    def test_empty_text_is_rejected(self):
        with self.assertRaises(ValueError):
            self.service.compare_lab_request("  ")


if __name__ == "__main__":
    unittest.main()
