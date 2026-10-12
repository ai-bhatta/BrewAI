const test = require("node:test");
const assert = require("node:assert/strict");
const { chooseNextDifficulty } = require("../frontend/bandit_policy.js");

test("bandit policy accepts a valid adjacent action", async () => {
  const result = await chooseNextDifficulty("normal", "easy", async () => ({ chosen_difficulty: "ambiguous" }));
  assert.equal(result.difficulty, "ambiguous");
  assert.equal(result.fallback, false);
});

test("bandit API/storage failure falls back to the heuristic choice", async () => {
  const result = await chooseNextDifficulty("normal", "easy", async () => { throw new Error("offline"); });
  assert.equal(result.difficulty, "easy");
  assert.equal(result.decision, null);
  assert.equal(result.fallback, true);
});

test("bandit response cannot bypass the one-level step limit", async () => {
  const result = await chooseNextDifficulty("easy", "normal", async () => ({ chosen_difficulty: "multi_clue" }));
  assert.equal(result.difficulty, "normal");
  assert.equal(result.decision, null);
  assert.equal(result.fallback, true);
});
