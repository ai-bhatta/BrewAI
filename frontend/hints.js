(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.BrewAIHints = api;
  }
})(globalThis, function () {
  const ATTRIBUTES = ["base", "milk", "sweetness", "topping", "vibe"];
  const LEVEL_COSTS = Object.freeze({ 1: 1, 2: 2, 3: 3 });
  const UNCERTAIN_THRESHOLD = 0.75;
  const PERSONA_WORDING = {
    coffee_snob: { nudge: "Think carefully about the {attribute} specification." },
    sleep_deprived_student: { nudge: "They definitely mentioned the {attribute}." },
  };

  function createHintState() {
    return { levelsByAttribute: {}, currentAttribute: null };
  }

  function selectHintTarget(confidences, levelsByAttribute = {}) {
    const remaining = ATTRIBUTES.filter((attribute) => (levelsByAttribute[attribute] || 0) < 3);
    remaining.sort((left, right) => {
      const leftLevel = levelsByAttribute[left] || 0;
      const rightLevel = levelsByAttribute[right] || 0;
      if ((leftLevel === 0) !== (rightLevel === 0)) return leftLevel === 0 ? -1 : 1;
      const leftConfidence = confidences?.[left];
      const rightConfidence = confidences?.[right];
      const leftHasConfidence = typeof leftConfidence === "number" && Number.isFinite(leftConfidence);
      const rightHasConfidence = typeof rightConfidence === "number" && Number.isFinite(rightConfidence);
      const leftUncertain = leftHasConfidence && leftConfidence < UNCERTAIN_THRESHOLD;
      const rightUncertain = rightHasConfidence && rightConfidence < UNCERTAIN_THRESHOLD;
      if (leftUncertain !== rightUncertain) return leftUncertain ? -1 : 1;
      if (leftUncertain && leftConfidence !== rightConfidence) return leftConfidence - rightConfidence;
      return ATTRIBUTES.indexOf(left) - ATTRIBUTES.indexOf(right);
    });
    return remaining[0] || null;
  }

  function describeHint(attribute, level, canonicalRecipe, personaId = "") {
    const value = canonicalRecipe?.[attribute];
    if (typeof value !== "string" || !LEVEL_COSTS[level]) return null;
    const title = attribute[0].toUpperCase() + attribute.slice(1);
    if (level === 3) return `${title} = ${value}`;

    if (level === 1) {
      const personaTemplate = PERSONA_WORDING[personaId]?.nudge;
      return personaTemplate
        ? personaTemplate.replace("{attribute}", attribute)
        : `Pay attention to what they said about ${attribute}.`;
    }

    const categories = {
      base: {
        espresso: "They want a coffee-based drink.",
        "cold brew": "They want a chilled coffee profile, not a short espresso-style shot.",
        matcha: "They are asking for a tea-based drink with a green-tea profile.",
        "milk tea": "They are asking for a tea-based drink.",
      },
      milk: {
        "whole milk": "They want dairy milk.",
        "oat milk": "They want a plant-based milk.",
        "almond milk": "They want a plant-based milk.",
        none: "Keep this order dairy-free without adding a milk alternative.",
      },
      sweetness: {
        "no sugar": "Keep sweetness on the restrained side.",
        "light sugar": "Keep sweetness on the restrained side.",
        "regular sugar": "They prefer a sweet drink, not a restrained one.",
        "extra sweet": "They prefer a sweet drink, not a restrained one.",
      },
      topping: {
        boba: "They want a chewy topping.",
        "coffee jelly": "They want a coffee-flavored topping.",
        foam: "They want a light, foamy topping.",
        none: "A topping isn't necessary; keep the finish simple.",
      },
      vibe: {
        classic: "Keep the drink familiar and classic.",
        cozy: "Aim for a warm, comforting feel.",
        energetic: "Give it an upbeat, lively feel.",
        experimental: "They want something more adventurous.",
      },
    };
    return categories[attribute]?.[value] || `Think about the ${attribute} they requested.`;
  }

  function advanceHint(hintState, level, canonicalRecipe, personaId = "", confidences = null, configuredCosts = LEVEL_COSTS) {
    const attribute = hintState.currentAttribute || selectHintTarget(confidences, hintState.levelsByAttribute);
    const currentLevel = hintState.levelsByAttribute[attribute] || 0;
    if (!attribute || level !== currentLevel + 1 || !Number.isFinite(Number(configuredCosts?.[level]))) return null;
    const message = describeHint(attribute, level, canonicalRecipe, personaId);
    if (!message) return null;
    const next = {
      levelsByAttribute: { ...hintState.levelsByAttribute, [attribute]: level },
      currentAttribute: level < 3 ? attribute : null,
    };
    if (level === 3) next.currentAttribute = selectHintTarget(confidences, next.levelsByAttribute);
    return { attribute, level, cost: Number(configuredCosts[level]), message, state: next };
  }

  return { ATTRIBUTES, LEVEL_COSTS, createHintState, selectHintTarget, describeHint, advanceHint };
});
