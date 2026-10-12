(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.BrewAIRushHour = api;
  }
})(globalThis, function () {
  function createRushHourShift(totalCustomers = 5, startingDifficulty = "normal") {
    return {
      totalCustomers,
      completedCustomers: 0,
      customersServed: 0,
      correctDrinks: 0,
      incorrectDrinks: 0,
      customersLost: 0,
      hintsUsed: 0,
      hintPointsSpent: 0,
      clarificationsUsed: 0,
      totalScore: 0,
      totalResponseTimeSeconds: 0,
      startingDifficulty,
      endingDifficulty: startingDifficulty,
      difficultyChanges: 0,
    };
  }

  function recordRushHourCustomer(shift, outcome, responseTimeSeconds, pointsAwarded = 0) {
    if (shift.completedCustomers >= shift.totalCustomers) {
      throw new Error("The Rush Hour shift is already complete.");
    }
    if (!["correct", "incorrect", "lost"].includes(outcome)) {
      throw new Error(`Unknown Rush Hour customer outcome: ${outcome}`);
    }

    const next = { ...shift };
    next.completedCustomers += 1;
    next.totalResponseTimeSeconds += Math.max(0, Number(responseTimeSeconds) || 0);
    next.totalScore += Number(pointsAwarded) || 0;
    if (outcome === "correct") {
      next.customersServed += 1;
      next.correctDrinks += 1;
    } else if (outcome === "incorrect") {
      next.customersServed += 1;
      next.incorrectDrinks += 1;
    } else {
      next.customersLost += 1;
    }
    return next;
  }

  function recordRushHourHint(shift, penalty = 3) {
    const cost = Math.max(0, Number(penalty) || 0);
    return {
      ...shift,
      hintsUsed: shift.hintsUsed + 1,
      hintPointsSpent: (shift.hintPointsSpent || 0) + cost,
      totalScore: Math.max(0, shift.totalScore - cost),
    };
  }

  function recordRushHourClarification(shift) {
    return { ...shift, clarificationsUsed: shift.clarificationsUsed + 1 };
  }

  function recordRushHourDifficulty(shift, difficulty) {
    const changed = shift.endingDifficulty !== difficulty;
    return {
      ...shift,
      endingDifficulty: difficulty,
      difficultyChanges: shift.difficultyChanges + (changed ? 1 : 0),
    };
  }

  function isRushHourComplete(shift) {
    return shift.completedCustomers >= shift.totalCustomers;
  }

  function summarizeRushHour(shift) {
    return {
      customersServed: shift.customersServed,
      totalCustomers: shift.totalCustomers,
      correctDrinks: shift.correctDrinks,
      incorrectDrinks: shift.incorrectDrinks,
      customersLost: shift.customersLost,
      hintsUsed: shift.hintsUsed,
      hintPointsSpent: shift.hintPointsSpent || 0,
      clarificationsUsed: shift.clarificationsUsed,
      totalScore: shift.totalScore,
      averageResponseTimeSeconds: shift.completedCustomers
        ? shift.totalResponseTimeSeconds / shift.completedCustomers
        : 0,
      startingDifficulty: shift.startingDifficulty || "normal",
      endingDifficulty: shift.endingDifficulty || shift.startingDifficulty || "normal",
      difficultyChanges: shift.difficultyChanges || 0,
    };
  }

  return {
    createRushHourShift,
    recordRushHourCustomer,
    recordRushHourHint,
    recordRushHourClarification,
    recordRushHourDifficulty,
    isRushHourComplete,
    summarizeRushHour,
  };
});
