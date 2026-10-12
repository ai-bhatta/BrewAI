import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from ai_service import BrewAIService


class GameEvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = BrewAIService.__new__(BrewAIService)
        self.ground_truth = {
            "base": "espresso",
            "milk": "oat milk",
            "sweetness": "light sugar",
            "topping": "boba",
            "vibe": "cozy",
        }

    def test_correct_player_drink_scores_full_points_when_ai_is_wrong(self) -> None:
        wrong_prediction = {
            "base": "cold brew",
            "milk": "whole milk",
            "sweetness": "extra sweet",
            "topping": "foam",
            "vibe": "energetic",
        }

        result = self.service.evaluate_order(
            self.ground_truth,
            wrong_prediction,
            self.ground_truth,
        )

        self.assertEqual(result.ai_matches, 0)
        self.assertEqual(result.player_matches, 5)
        self.assertEqual(result.points_awarded, 120)

    def test_ai_accuracy_is_reported_separately_from_player_score(self) -> None:
        result = self.service.evaluate_order(
            self.ground_truth,
            self.ground_truth,
            {**self.ground_truth, "base": "matcha"},
        )

        self.assertEqual(result.ai_matches, 5)
        self.assertEqual(result.player_matches, 4)
        self.assertEqual(result.points_awarded, 75)

    def test_prediction_returns_confidence_per_attribute_without_rescaling(self) -> None:
        class FakeModel:
            def predict(self, _texts):
                return ["predicted"]

            def predict_proba(self, _texts):
                return [[0.2, 0.8]]

        self.service.model_bundle = {
            "models": {label: FakeModel() for label in self.ground_truth}
        }

        recipe, confidence = self.service._predict_with_model("test order")

        self.assertEqual(recipe, {label: "predicted" for label in self.ground_truth})
        self.assertEqual(confidence, {label: 0.8 for label in self.ground_truth})

    def test_interpretation_response_preserves_persona_metadata(self) -> None:
        self.service.model_loaded = False
        persona = {
            "persona": "coffee_snob",
            "display_name": "Coffee Snob",
            "character_label": "Knows the details",
            "patience": 0.68,
            "verbosity": 0.4,
            "ambiguity": 0.06,
            "coffee_knowledge": 0.96,
            "preferred_wording": ["Let's be precise"],
        }

        response = self.service.interpret_order(
            "Alex",
            "espresso with oat milk, light sugar, boba, cozy",
            persona,
        )

        self.assertEqual(response.persona, "coffee_snob")
        self.assertEqual(response.patience, 0.68)
        self.assertEqual(response.preferred_wording, ["Let's be precise"])


if __name__ == "__main__":
    unittest.main()
