import asyncio
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.error import URLError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from customer_generation_repository import CustomerGenerationRepository
from customer_generation_service import CustomerGenerationService, validate_customer_request


class CustomerGenerationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = self.root / "customer_generation.json"
        self.config.write_text(json.dumps({
            "enabled": True, "mode": "auto", "base_url": "http://127.0.0.1:11434",
            "model": "test-model", "timeout_seconds": 1, "maximum_request_characters": 220,
        }), encoding="utf-8")
        self.repository = CustomerGenerationRepository(self.root / "cache.sqlite3")
        self.calls = 0
        self.service = CustomerGenerationService(self.repository, self.config, self.transport)
        self.recipe = {"base": "espresso", "milk": "oat milk", "sweetness": "light sugar", "topping": "boba", "vibe": "cozy"}
        self.persona = {"id": "coffee_snob", "display_name": "Coffee Snob", "preferred_wording": ["precisely"], "coffee_knowledge": .9, "verbosity": .4}

    def tearDown(self):
        self.temp.cleanup()

    def transport(self, *_args):
        self.calls += 1
        return "Espresso with oat milk, light sugar, boba, and a cozy feel, please."

    def payload(self):
        return {"canonical_recipe": self.recipe, "persona": self.persona, "difficulty": "normal", "mode": "local_ai"}

    def test_validated_generation_preserves_canonical_input_and_is_cached(self):
        original = dict(self.recipe)
        first = asyncio.run(self.service.generate(self.payload()))
        second = asyncio.run(self.service.generate(self.payload()))
        self.assertTrue(first["success"])
        self.assertFalse(first["cache_hit"])
        self.assertTrue(second["cache_hit"])
        self.assertEqual(self.calls, 1)
        self.assertEqual(self.recipe, original)

    def test_ollama_unavailable_falls_back_without_raising(self):
        self.service.transport = lambda *_args: (_ for _ in ()).throw(URLError("offline"))
        result = asyncio.run(self.service.generate(self.payload()))
        self.assertFalse(result["success"])
        self.assertEqual(result["source"], "template")
        self.assertEqual(result["fallback_reason"], "ollama_unavailable")

    def test_slow_transport_returns_timeout_fallback(self):
        config = json.loads(self.config.read_text(encoding="utf-8"))
        config["timeout_seconds"] = 0.5
        self.config.write_text(json.dumps(config), encoding="utf-8")
        self.service.transport = lambda *_args: (time.sleep(1), "late response")[1]
        result = asyncio.run(self.service.generate(self.payload()))
        self.assertEqual(result["fallback_reason"], "timeout")

    def test_contradictory_or_missing_attribute_text_is_rejected(self):
        bad = "Espresso with whole milk, light sugar, boba, and a cozy feel."
        result = validate_customer_request(bad, self.recipe)
        self.assertFalse(result["valid"])
        self.assertTrue(result["contradiction"])

    def test_regular_sweetness_synonym_does_not_conflict_with_light_sugar(self):
        result = validate_customer_request("Espresso with oat milk, slightly sweet, boba, cozy.", self.recipe)
        self.assertTrue(result["valid"])

    def test_external_ollama_hosts_are_rejected(self):
        config = json.loads(self.config.read_text(encoding="utf-8"))
        config["base_url"] = "https://example.com"
        self.config.write_text(json.dumps(config), encoding="utf-8")
        with self.assertRaises(ValueError):
            self.service.config()

    def test_invalid_canonical_values_are_rejected(self):
        payload = self.payload()
        payload["canonical_recipe"] = {**self.recipe, "topping": "cinnamon"}
        with self.assertRaises(ValueError):
            asyncio.run(self.service.generate(payload))


if __name__ == "__main__":
    unittest.main()
