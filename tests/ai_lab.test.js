const test = require("node:test");
const assert = require("node:assert/strict");
const utils = require("../frontend/ai_lab_utils.js");

test("free-form analysis payload omits ground truth unless explicitly supplied", () => {
  assert.deepEqual(utils.createAnalysisPayload("  oat latte  "), { text: "oat latte" });
  assert.deepEqual(utils.createAnalysisPayload("oat latte", { milk: "oat milk" }), {
    text: "oat latte",
    ground_truth: { milk: "oat milk" },
  });
});

test("labeled robustness examples expose canonical attributes", () => {
  const example = utils.getExampleInput({ utterance: "espresso, oat milk", base: "espresso", milk: "oat milk" });
  assert.deepEqual(example, {
    text: "espresso, oat milk",
    groundTruth: { base: "espresso", milk: "oat milk" },
  });
  assert.equal(utils.getExampleInput({ category: "typo" }), null);
});

test("confidence average uses available numeric values only", () => {
  assert.equal(utils.averageConfidence({ confidence: { base: 0.8, milk: 0.6, vibe: null } }), 0.7);
  assert.equal(utils.averageConfidence({ confidence: null }), null);
});

test("disagreement view omits unavailable models and finds attribute conflicts", () => {
  const models = {
    keyword_rules: { available: true, prediction: { milk: "oat milk" } },
    multinomial_nb: { available: true, prediction: { milk: "whole milk" } },
    logistic_regression: { available: false, prediction: null },
    linear_svm: { available: true, prediction: { milk: "oat milk" } },
  };
  assert.deepEqual(utils.findDisagreements(models), [{
    attribute: "milk",
    predictions: [
      { model: "keyword_rules", value: "oat milk" },
      { model: "multinomial_nb", value: "whole milk" },
      { model: "linear_svm", value: "oat milk" },
    ],
  }]);
});

test("ground-truth comparison and partial model response normalization are safe", () => {
  const comparison = utils.compareWithGroundTruth({
    keyword_rules: { prediction: { base: "espresso" } },
  }, { base: "espresso" });
  assert.equal(comparison.keyword_rules.base, true);
  const normalized = utils.normalizeComparisonResponse({ models: { keyword_rules: { available: true } } });
  assert.equal(normalized.models.linear_svm.available, false);
  assert.throws(() => utils.normalizeComparisonResponse({}), /did not contain model results/);
});
