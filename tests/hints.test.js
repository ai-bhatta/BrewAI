const test = require("node:test");
const assert = require("node:assert/strict");
const {
  LEVEL_COSTS,
  createHintState,
  selectHintTarget,
  advanceHint,
  describeHint,
} = require("../frontend/hints.js");

const canonical = {
  base: "espresso",
  milk: "oat milk",
  sweetness: "light sugar",
  topping: "boba",
  vibe: "cozy",
};

test("each hint level has its configured point cost", () => {
  assert.deepEqual(LEVEL_COSTS, { 1: 1, 2: 2, 3: 3 });
});

test("experiment-specific hint costs override defaults without changing hint strength", () => {
  const hinted = advanceHint(createHintState(), 1, canonical, "", null, { 1: 1, 2: 1, 3: 2 });
  assert.equal(hinted.cost, 1);
  const strong = advanceHint(hinted.state, 2, canonical, "", null, { 1: 1, 2: 1, 3: 2 });
  assert.equal(strong.cost, 1);
  const reveal = advanceHint(strong.state, 3, canonical, "", null, { 1: 1, 2: 1, 3: 2 });
  assert.equal(reveal.cost, 2);
  assert.match(reveal.message, / = /);
});

test("hint wording uses canonical truth and progresses without repeating a weak level", () => {
  const predicted = { ...canonical, milk: "almond milk" };
  let hintState = createHintState();
  hintState.currentAttribute = "milk";

  const nudge = advanceHint(hintState, 1, canonical);
  assert.equal(nudge.attribute, "milk");
  assert.equal(nudge.cost, 1);
  assert.doesNotMatch(nudge.message, /oat|almond/i);
  assert.equal(advanceHint(nudge.state, 1, canonical), null);

  const strong = advanceHint(nudge.state, 2, canonical);
  assert.equal(strong.cost, 2);
  assert.match(strong.message, /plant-based/i);
  assert.doesNotMatch(strong.message, /oat|almond/i);

  const reveal = advanceHint(strong.state, 3, canonical);
  assert.equal(reveal.cost, 3);
  assert.equal(reveal.message, "Milk = oat milk");
  assert.notEqual(reveal.message, `Milk = ${predicted.milk}`);
});

test("target selection prefers uncertain unused attributes and has deterministic fallback", () => {
  const levels = { topping: 3 };
  assert.equal(selectHintTarget({ milk: 0.8, sweetness: 0.2 }, levels), "sweetness");
  assert.equal(selectHintTarget(null, {}), "base");
  assert.equal(selectHintTarget(null, { base: 3, milk: 1 }), "sweetness");
});

test("persona wording varies deterministically without changing the canonical answer", () => {
  assert.match(describeHint("milk", 1, canonical, "coffee_snob"), /specification/);
  assert.match(describeHint("milk", 1, canonical, "sleep_deprived_student"), /definitely/);
  assert.equal(describeHint("milk", 3, canonical, "coffee_snob"), "Milk = oat milk");
});
