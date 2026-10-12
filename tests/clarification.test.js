const test = require("node:test");
const assert = require("node:assert/strict");
const {
  CONFIG,
  getConfidenceStatus,
  selectClarificationAttribute,
  createClarificationReply,
  applyClarificationTimePenalty,
} = require("../frontend/clarification.js");

test("selects the lowest-confidence eligible attribute and skips clarified attributes", () => {
  const confidences = { base: 0.72, milk: 0.91, sweetness: 0.48, topping: 0.31, vibe: 0.66 };
  assert.equal(selectClarificationAttribute(confidences), "topping");
  assert.equal(selectClarificationAttribute(confidences, ["topping"]), "sweetness");
});

test("clarification replies use only the requested canonical attribute", () => {
  const truth = { base: "matcha", milk: "oat milk", sweetness: "light sugar", topping: "cinnamon", vibe: "cozy" };
  const predicted = { ...truth, topping: "boba" };
  assert.equal(createClarificationReply("topping", truth), "cinnamon would be great.");
  assert.notEqual(createClarificationReply("topping", truth), predicted.topping);
  assert.equal(createClarificationReply("unknown", truth), null);
});

test("confidence status uses configured thresholds and missing values stay unavailable", () => {
  assert.equal(getConfidenceStatus(CONFIG.HIGH_CONFIDENCE), "confident");
  assert.equal(getConfidenceStatus(CONFIG.LOW_CONFIDENCE), "uncertain");
  assert.equal(getConfidenceStatus(0.2), "very-uncertain");
  assert.equal(getConfidenceStatus(null), "unavailable");
  assert.equal(selectClarificationAttribute(null), null);
  assert.equal(selectClarificationAttribute({ topping: null }), null);
});

test("clarification penalty is configurable and never makes the timer negative", () => {
  assert.equal(applyClarificationTimePenalty(10), 7);
  assert.equal(applyClarificationTimePenalty(2), 0);
  assert.equal(applyClarificationTimePenalty(20, 5), 15);
});
