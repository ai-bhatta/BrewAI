import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ProductionMetadataTests(unittest.TestCase):
    def test_metadata_identifies_exact_dataset_and_heldout_scope(self):
        dataset_path = ROOT / "data" / "order_dataset.json"
        metadata_path = ROOT / "results" / "production_model_metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        dataset_hash = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
        self.assertEqual(metadata["canonical_dataset"], "data/order_dataset.json")
        self.assertEqual(metadata["dataset_sha256"], dataset_hash)
        self.assertEqual(metadata["training_examples"], metadata["split"]["train_count"])
        self.assertEqual(metadata["holdout_examples"], metadata["split"]["test_count"])
        self.assertIn("holdout excluded", metadata["evaluation_method"])
        self.assertIn("macro_f1", metadata)


if __name__ == "__main__":
    unittest.main()
