(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.BrewAIClarification = api;
  }
})(globalThis, function () {
  const CONFIG = Object.freeze({
    HIGH_CONFIDENCE: 0.75,
    LOW_CONFIDENCE: 0.5,
    CLARIFICATION_TIME_PENALTY_SECONDS: 3,
  });

  const ATTRIBUTE_ORDER = ["base", "milk", "sweetness", "topping", "vibe"];

  function getConfidenceStatus(confidence) {
    if (typeof confidence !== "number" || !Number.isFinite(confidence)) return "unavailable";
    if (confidence >= CONFIG.HIGH_CONFIDENCE) return "confident";
    if (confidence >= CONFIG.LOW_CONFIDENCE) return "uncertain";
    return "very-uncertain";
  }

  function selectClarificationAttribute(confidences, clarifiedAttributes = []) {
    const clarified = clarifiedAttributes instanceof Set
      ? clarifiedAttributes
      : new Set(clarifiedAttributes);
    return ATTRIBUTE_ORDER
      .filter((attribute) => !clarified.has(attribute))
      .map((attribute) => ({ attribute, confidence: confidences?.[attribute] }))
      .filter(({ confidence }) =>
        typeof confidence === "number" && Number.isFinite(confidence) &&
        confidence >= 0 && confidence < CONFIG.HIGH_CONFIDENCE)
      .sort((left, right) => left.confidence - right.confidence)[0]?.attribute || null;
  }

  function createClarificationReply(attribute, canonicalRecipe) {
    const value = canonicalRecipe?.[attribute];
    if (typeof value !== "string") return null;
    const answers = {
      base: `I'd like ${value}, please.`,
      milk: value === "none" ? "No milk, please." : `${value}, please.`,
      sweetness: `${value}, please.`,
      topping: value === "none" ? "No topping, please." : `${value} would be great.`,
      vibe: `Something ${value}, please.`,
    };
    return answers[attribute] || null;
  }

  function applyClarificationTimePenalty(timeLeft, penalty = CONFIG.CLARIFICATION_TIME_PENALTY_SECONDS) {
    return Math.max(0, (Number(timeLeft) || 0) - Math.max(0, Number(penalty) || 0));
  }

  return {
    CONFIG,
    getConfidenceStatus,
    selectClarificationAttribute,
    createClarificationReply,
    applyClarificationTimePenalty,
  };
});
