const test = require("node:test");
const assert = require("node:assert/strict");
const {
  createRushHourShift,
  recordRushHourCustomer,
  recordRushHourHint,
  recordRushHourClarification,
  recordRushHourDifficulty,
  isRushHourComplete,
  summarizeRushHour,
} = require("../frontend/rush_hour.js");

test("Rush Hour progresses through five customer outcomes", () => {
  let shift = createRushHourShift();
  shift = recordRushHourCustomer(shift, "correct", 10, 120);
  shift = recordRushHourCustomer(shift, "incorrect", 20, 75);
  shift = recordRushHourCustomer(shift, "lost", 30, 0);
  shift = recordRushHourCustomer(shift, "correct", 12, 120);
  assert.equal(isRushHourComplete(shift), false);
  shift = recordRushHourCustomer(shift, "lost", 28, 0);
  assert.equal(isRushHourComplete(shift), true);
});

test("shift summary counts outcomes, hints, points, and average response time", () => {
  let shift = createRushHourShift(3);
  shift = recordRushHourCustomer(shift, "correct", 10, 120);
  shift = recordRushHourHint(shift, 3);
  shift = recordRushHourClarification(shift);
  shift = recordRushHourCustomer(shift, "incorrect", 20, 75);
  shift = recordRushHourCustomer(shift, "lost", 30, 0);

  assert.deepEqual(summarizeRushHour(shift), {
    customersServed: 2,
    totalCustomers: 3,
    correctDrinks: 1,
    incorrectDrinks: 1,
    customersLost: 1,
    hintsUsed: 1,
    hintPointsSpent: 3,
    clarificationsUsed: 1,
    totalScore: 192,
    averageResponseTimeSeconds: 20,
    startingDifficulty: "normal",
    endingDifficulty: "normal",
    difficultyChanges: 0,
  });
});

test("Rush Hour tracks starting difficulty, ending difficulty, and number of changes", () => {
  let shift = createRushHourShift(5, "normal");
  shift = recordRushHourDifficulty(shift, "ambiguous");
  shift = recordRushHourDifficulty(shift, "ambiguous");
  shift = recordRushHourDifficulty(shift, "slang");
  const summary = summarizeRushHour(shift);
  assert.equal(summary.startingDifficulty, "normal");
  assert.equal(summary.endingDifficulty, "slang");
  assert.equal(summary.difficultyChanges, 2);
});

test("Rush Hour counts progressive hint use and clamps score deductions", () => {
  let shift = createRushHourShift(2);
  shift = recordRushHourCustomer(shift, "correct", 10, 4);
  shift = recordRushHourHint(shift, 1);
  shift = recordRushHourHint(shift, 2);
  shift = recordRushHourHint(shift, 3);
  const summary = summarizeRushHour(shift);
  assert.equal(summary.hintsUsed, 3);
  assert.equal(summary.hintPointsSpent, 6);
  assert.equal(summary.totalScore, 0);
});

test("a shift rejects extra customers after completion", () => {
  let shift = createRushHourShift(1);
  shift = recordRushHourCustomer(shift, "lost", 30);
  assert.throws(() => recordRushHourCustomer(shift, "correct", 10), /already complete/);
});
