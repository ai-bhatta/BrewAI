import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from feedback_repository import DuplicateFeedbackError, FeedbackRepository
from feedback_service import FeedbackService, FeedbackValidationError
from ml.compare_models import grouped_holdout_split, load_dataset
from ml.retrain_with_feedback import compare_evaluations, evaluate_candidate
import joblib


class FeedbackWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = FeedbackRepository(Path(self.temp.name) / "feedback.sqlite3")
        self.service = FeedbackService(self.repo)
        record = load_dataset()[0]
        self.predicted = {key: record[key] for key in ("base", "milk", "sweetness", "topping", "vibe")}
        self.corrected = dict(self.predicted)
        self.corrected["milk"] = "none" if self.predicted["milk"] != "none" else "oat milk"
        self.payload = {
            "text": "A completely new human correction request.",
            "model": "linear_svm",
            "predicted": self.predicted,
            "corrected": self.corrected,
            "confidence": {"milk": 0.31},
            "model_disagreement": True,
        }

    def tearDown(self):
        self.temp.cleanup()

    def test_valid_correction_is_pending_and_preserves_human_truth(self):
        result = self.service.submit(self.payload)["feedback"]
        self.assertTrue(result["id"])
        self.assertEqual(result["status"], "pending")
        self.assertEqual(result["corrected"], self.corrected)
        self.assertEqual(result["source"], "ai_lab")
        self.assertEqual(result["priority"], 1)
        self.assertTrue(result["low_confidence"])

    def test_invalid_values_missing_prediction_and_identical_correction_are_rejected(self):
        invalid = {**self.payload, "corrected": {**self.corrected, "milk": "camel milk"}}
        with self.assertRaises(FeedbackValidationError):
            self.service.submit(invalid)
        missing = {**self.payload, "predicted": {"milk": "oat milk"}}
        with self.assertRaises(FeedbackValidationError):
            self.service.submit(missing)
        identical = {**self.payload, "corrected": self.predicted}
        with self.assertRaises(FeedbackValidationError):
            self.service.submit(identical)

    def test_exact_duplicate_is_rejected_after_text_normalization(self):
        self.service.submit(self.payload)
        duplicate = {**self.payload, "text": f"  {self.payload['text'].upper()}  "}
        with self.assertRaises(DuplicateFeedbackError):
            self.service.submit(duplicate)

    def test_pending_entry_can_be_approved_or_rejected_and_only_approved_is_promoted(self):
        approved_id = self.service.submit(self.payload)["feedback"]["id"]
        second = {**self.payload, "text": "Second distinct correction request."}
        rejected_id = self.service.submit(second)["feedback"]["id"]
        self.assertEqual(self.service.review(approved_id, "approved")["status"], "approved")
        self.assertEqual(self.service.review(rejected_id, "rejected")["status"], "rejected")
        promoted = self.repo.approved_examples()
        self.assertEqual(len(promoted), 1)
        self.assertEqual(promoted[0]["milk"], self.corrected["milk"])
        self.assertEqual(self.repo.review(rejected_id, "approved"), None)

    def test_similar_text_is_returned_as_review_warning(self):
        self.service.submit(self.payload)
        similar = {**self.payload, "text": "A completely new human correction request"}
        result = self.service.submit(similar)
        self.assertTrue(result["similar_entries"])

    def test_feedback_api_handlers_submit_list_approve_and_reject(self):
        import main
        from schemas import FeedbackCreateRequest

        original_service = main.feedback_service
        main.feedback_service = self.service
        try:
            created = main.submit_feedback(FeedbackCreateRequest(**self.payload))
            self.assertEqual(created.feedback.status, "pending")
            self.assertEqual(len(main.list_feedback("pending").entries), 1)
            approved = main.approve_feedback(created.feedback.id)
            self.assertEqual(approved.status, "approved")
            rejected_payload = {**self.payload, "text": "API reject-path request"}
            rejected = main.submit_feedback(FeedbackCreateRequest(**rejected_payload))
            self.assertEqual(main.reject_feedback(rejected.feedback.id).status, "rejected")
        finally:
            main.feedback_service = original_service

    def test_malformed_stored_record_does_not_break_queue(self):
        self.repo.create({**self.payload, "priority": 1, "low_confidence": True})
        connection = self.repo._connect()
        try:
            connection.execute("UPDATE feedback SET corrected = '{broken' WHERE status='pending'")
            connection.commit()
        finally:
            connection.close()
        self.assertEqual(self.repo.list_entries(), [])

    def test_candidate_uses_approved_feedback_and_never_overwrites_source_or_production(self):
        records = load_dataset()
        original_hash = hashlib.sha256((ROOT / "data" / "order_dataset.json").read_bytes()).hexdigest()
        production_path = ROOT / "backend" / "model" / "order_parser.joblib"
        production_hash = hashlib.sha256(production_path.read_bytes()).hexdigest()
        train_indices, _test_indices, _metadata = grouped_holdout_split(records)
        source = records[int(train_indices[0])]
        example = {"id": "approved-test-id", "utterance": "brand new reviewed training sample words"}
        example.update({key: source[key] for key in self.predicted})
        bad_example = {"id": "bad-id", "utterance": "broken feedback", **{key: "unsupported" for key in self.predicted}}
        with tempfile.TemporaryDirectory() as output:
            report = evaluate_candidate(
                "logistic_regression", records=records,
                approved_examples=[example, bad_example],
                baseline_bundle=joblib.load(production_path),
                candidate_dir=Path(output) / "candidates",
                results_dir=Path(output) / "results",
            )
            candidate_path = Path(report["candidate_artifact"])
            self.assertTrue(candidate_path.exists())
            self.assertEqual(report["candidate_artifact_metadata"]["artifact_version"], 1)
            self.assertEqual(len(report["candidate_artifact_metadata"]["feedback_examples_sha256"]), 64)
            saved_candidate = joblib.load(candidate_path)
            self.assertEqual(saved_candidate["artifact_version"], 1)
            self.assertEqual(report["feedback_examples"], 1)
            self.assertEqual(report["invalid_feedback_examples"], 1)
            self.assertIn("milk", report["candidate"]["grouped_holdout"]["per_attribute_macro_f1"])
            self.assertEqual(report["recommendation"], "review")
            self.assertEqual(report["baseline"]["grouped_holdout"]["example_count"], report["candidate"]["grouped_holdout"]["example_count"])
            self.assertEqual(report["no_feedback_control"]["grouped_holdout"]["example_count"], report["candidate"]["grouped_holdout"]["example_count"])
            self.assertFalse(report["evaluation"]["original_dataset_modified"])
            self.assertFalse(report["evaluation"]["production_model_modified"])
        self.assertEqual(original_hash, hashlib.sha256((ROOT / "data" / "order_dataset.json").read_bytes()).hexdigest())
        self.assertEqual(production_hash, hashlib.sha256(production_path.read_bytes()).hexdigest())

    def test_candidate_fails_cleanly_when_no_approved_feedback_exists(self):
        with self.assertRaisesRegex(ValueError, "No approved feedback"):
            evaluate_candidate(approved_examples=[])

    def test_attribute_regressions_are_explicitly_reported(self):
        baseline = {key: {"macro_f1": 0.8, "per_attribute_macro_f1": {name: 0.8 for name in self.predicted}} for key in ("grouped_holdout", "challenge_set")}
        candidate = {key: {"macro_f1": 0.78, "per_attribute_macro_f1": {**{name: 0.8 for name in self.predicted}, "topping": 0.7}} for key in baseline}
        _improvements, regressions = compare_evaluations(baseline, candidate)
        self.assertTrue(any(item["attribute"] == "topping" and item["evaluation"] == "grouped_holdout" for item in regressions))
        self.assertTrue(any(item["attribute"] == "overall" for item in regressions))


if __name__ == "__main__":
    unittest.main()
