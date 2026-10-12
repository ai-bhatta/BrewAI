const test = require("node:test");
const assert = require("node:assert/strict");
const {
  CONFIG,
  createPerformanceState,
  recordOrder,
  summarizePerformance,
  evaluateDifficulty,
} = require("../frontend/difficulty_engine.js");

function buildHistory(initialDifficulty, orders) {
  return orders.reduce(recordOrder, createPerformanceState(initialDifficulty));
}

const goodFast = { accuracy: 1, responseTimeSeconds: 9, hintsUsed: 0, clarificationsUsed: 0, correct: true };
const poor = { accuracy: 0.4, responseTimeSeconds: 18, hintsUsed: 0, clarificationsUsed: 0, correct: false, mistakeAttributes: ["milk"] };

test("insufficient history keeps the selected starting difficulty", () => {
  const state = buildHistory("normal", [goodFast, goodFast]);
  const result = evaluateDifficulty(state);
  assert.equal(result.decision.next, "normal");
  assert.equal(result.decision.reason, "insufficient_history");
});

test("strong accurate and fast performance raises difficulty by one level", () => {
  const state = buildHistory("normal", [goodFast, goodFast, goodFast]);
  const result = evaluateDifficulty(state);
  assert.equal(result.decision.next, "ambiguous");
  assert.equal(result.decision.reason, "high_accuracy");
  assert.equal(result.decision.changed, true);
});

test("poor accuracy lowers difficulty by one level and identifies repeated mistakes", () => {
  const state = buildHistory("normal", [poor, poor, poor]);
  const result = evaluateDifficulty(state);
  assert.equal(result.decision.next, "easy");
  assert.equal(result.decision.reason, "low_accuracy");
  assert.deepEqual(summarizePerformance(state).recentMistakeAttributes, ["milk"]);
  assert.equal(evaluateDifficulty(createPerformanceState("easy")).decision.next, "easy");
});

test("frequent hints and clarification independently reduce difficulty", () => {
  const hinted = buildHistory("slang", Array.from({ length: 3 }, () => ({ ...goodFast, hintsUsed: 1 })));
  const clarified = buildHistory("slang", Array.from({ length: 3 }, () => ({ ...goodFast, clarificationsUsed: 1 })));
  assert.equal(evaluateDifficulty(hinted).decision.reason, "high_hint_usage");
  assert.equal(evaluateDifficulty(hinted).decision.next, "ambiguous");
  assert.equal(evaluateDifficulty(clarified).decision.reason, "high_clarification_usage");
  assert.equal(evaluateDifficulty(clarified).decision.next, "ambiguous");
});

test("slow response encourages an easier order while a correct streak raises it gradually", () => {
  const slow = buildHistory("negation", Array.from({ length: 3 }, () => ({ ...goodFast, responseTimeSeconds: CONFIG.SLOW_RESPONSE_SECONDS })));
  const steadyCorrect = { ...goodFast, accuracy: 0.8 };
  const streak = buildHistory("ambiguous", [steadyCorrect, steadyCorrect, steadyCorrect]);
  assert.equal(evaluateDifficulty(slow).decision.reason, "slow_response");
  assert.equal(evaluateDifficulty(slow).decision.next, "slang");
  assert.equal(evaluateDifficulty(streak).decision.next, "slang");
  assert.equal(evaluateDifficulty(streak).decision.reason, "winning_streak");
  assert.equal(evaluateDifficulty(createPerformanceState("multi_clue")).decision.next, "multi_clue");
});

test("the same history produces the same decision and never jumps multiple levels", () => {
  const state = buildHistory("easy", [goodFast, goodFast, goodFast]);
  const first = evaluateDifficulty(state);
  const second = evaluateDifficulty(state);
  assert.deepEqual(first.decision, second.decision);
  assert.equal(first.decision.next, "normal");
});

test("adaptive OFF preserves the selected fixed difficulty regardless of history", () => {
  const state = buildHistory("easy", [poor, poor, poor]);
  const result = evaluateDifficulty(state, { adaptiveEnabled: false, fixedDifficulty: "negation" });
  assert.equal(result.decision.next, "negation");
  assert.equal(result.decision.reason, "adaptive_disabled");
});

test("performance history is bounded to the recent rolling window", () => {
  const state = buildHistory("normal", Array.from({ length: 8 }, () => goodFast));
  assert.equal(state.history.length, CONFIG.HISTORY_LIMIT);
});
