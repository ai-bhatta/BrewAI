(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.BrewAIBanditPolicy = api;
})(globalThis, function () {
  const LEVELS = ["easy", "normal", "ambiguous", "slang", "negation", "multi_clue"];

  async function chooseNextDifficulty(current, heuristicAction, requestDecision) {
    const currentIndex = LEVELS.indexOf(current);
    const baselineIndex = LEVELS.indexOf(heuristicAction);
    const safeBaseline = baselineIndex >= 0 && currentIndex >= 0 && Math.abs(baselineIndex - currentIndex) <= 1
      ? heuristicAction
      : LEVELS[Math.max(0, Math.min(LEVELS.length - 1, currentIndex))];
    try {
      const decision = await requestDecision();
      const chosenIndex = LEVELS.indexOf(decision?.chosen_difficulty);
      if (chosenIndex < 0 || currentIndex < 0 || Math.abs(chosenIndex - currentIndex) > 1) {
        return { difficulty: safeBaseline, decision: null, fallback: true };
      }
      return { difficulty: decision.chosen_difficulty, decision, fallback: false };
    } catch (_error) {
      return { difficulty: safeBaseline, decision: null, fallback: true };
    }
  }

  return { LEVELS, chooseNextDifficulty };
});
