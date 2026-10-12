(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.BrewAIPersonas = api;
  }
})(globalThis, function () {
  const PERSONAS = {
    executive: {
      id: "executive",
      display_name: "Executive",
      character_label: "Focused and concise",
      patience: 0.62,
      verbosity: 0.24,
      ambiguity: 0.08,
      coffee_knowledge: 0.72,
      preferred_wording: ["Quick order", "Please prepare", "For takeaway"],
      templates: [
        "{opening}: {base}, {milk}, {sweetness}, {topping}. Keep it {vibe}, please.",
        "{opening} {base} with {milk}, {sweetness}, and {topping}. A {vibe} profile.",
        "{opening}: {base}; {milk}; {sweetness}; {topping}. Keep the mood {vibe}.",
      ],
    },
    sleep_deprived_student: {
      id: "sleep_deprived_student",
      display_name: "Sleep-Deprived Student",
      character_label: "Running on caffeine",
      patience: 0.76,
      verbosity: 0.66,
      ambiguity: 0.3,
      coffee_knowledge: 0.35,
      preferred_wording: ["Bro", "Please save me", "I have an exam soon"],
      templates: [
        "{opening}, {base} with {milk}, {sweetness}, and {topping}. Keep it {vibe}; I need to stay awake.",
        "{opening} with {base}: {milk}, {sweetness}, {topping}. Make the vibe {vibe}.",
        "{opening}. {base}, {milk}, {sweetness}, {topping}, and a {vibe} feel, please.",
      ],
    },
    influencer: {
      id: "influencer",
      display_name: "Influencer",
      character_label: "Here for the aesthetic",
      patience: 1.0,
      verbosity: 0.7,
      ambiguity: 0.42,
      coffee_knowledge: 0.48,
      preferred_wording: ["Can you make me", "I'm thinking", "Maybe"],
      templates: [
        "{opening} {base} with {milk}, {sweetness}, and {topping}? Cute {vibe} vibes, please.",
        "{opening} {base}, {milk}, {sweetness}, {topping}, with a {vibe} mood. Make it camera-ready!",
        "{opening} {base}? Use {milk}, {sweetness}, and {topping}; I want it to feel {vibe}.",
      ],
    },
    coffee_snob: {
      id: "coffee_snob",
      display_name: "Coffee Snob",
      character_label: "Knows the details",
      patience: 0.68,
      verbosity: 0.4,
      ambiguity: 0.06,
      coffee_knowledge: 0.96,
      preferred_wording: ["A precise order", "Let's be precise", "For the cup"],
      templates: [
        "{opening}: {base}, {milk}, {sweetness}, {topping}. Keep the profile {vibe}; don't drown the main flavor.",
        "{opening}: {base} prepared with {milk}, {sweetness}, and {topping}. A clean {vibe} finish.",
        "{opening}: {base}, {milk}, {sweetness}, {topping}. Keep it {vibe}.",
      ],
    },
    indecisive_customer: {
      id: "indecisive_customer",
      display_name: "Indecisive Customer",
      character_label: "Still deciding",
      patience: 1.12,
      verbosity: 0.72,
      ambiguity: 0.82,
      coffee_knowledge: 0.42,
      preferred_wording: ["I'm torn", "Could we do", "Maybe"],
      templates: [
        "{opening}, but let's go with {base}; {milk}, {sweetness}, and {topping}. Maybe {vibe}?",
        "{opening} {base} with {milk}, {sweetness}, and {topping}? I think {vibe} sounds right.",
        "{opening} {base}? Actually, {milk}, {sweetness}, {topping}, and something {vibe}, please.",
      ],
    },
  };

  const BASE_WORDING = {
    espresso: ["espresso", "strong espresso"],
    "cold brew": ["iced cold brew", "cold brew coffee"],
    matcha: ["matcha drink", "matcha"],
    "milk tea": ["milk tea", "bubble tea"],
  };
  const OPTIONAL_HEDGES = ["I guess", "Perhaps", "I'm leaning toward"];
  const CONTEXT_LINES = [
    "I'm on a tight schedule.",
    "It's been a long day.",
    "I'm trying something new today.",
    "Thanks for making it just right.",
  ];
  const DIFFICULTY_WORDING = {
    easy: {
      base: { espresso: "espresso", "cold brew": "cold brew", matcha: "matcha", "milk tea": "milk tea" },
      milk: { "whole milk": "whole milk", "oat milk": "oat milk", "almond milk": "almond milk", none: "no milk" },
      sweetness: { "no sugar": "no sugar", "light sugar": "light sugar", "regular sugar": "regular sugar", "extra sweet": "extra sweet" },
      topping: { boba: "boba", "coffee jelly": "coffee jelly", foam: "foam", none: "no topping" },
      vibe: { classic: "classic", cozy: "cozy", energetic: "energetic", experimental: "experimental" },
    },
    ambiguous: {
      base: { espresso: "something coffee-forward", "cold brew": "something cold and coffee-forward", matcha: "a green-tea drink", "milk tea": "a tea-based drink" },
      milk: { "whole milk": "something creamy", "oat milk": "a plant-based milk", "almond milk": "a nutty plant milk", none: "no milk" },
      sweetness: { "no sugar": "not sweet", "light sugar": "slightly sweet", "regular sugar": "sweet", "extra sweet": "quite sweet" },
      topping: { boba: "something chewy", "coffee jelly": "a coffee-flavored add-in", foam: "a soft topping", none: "no topping" },
      vibe: { classic: "a familiar feel", cozy: "a comforting feel", energetic: "an upbeat feel", experimental: "an adventurous feel" },
    },
    slang: {
      base: { espresso: "something strong", "cold brew": "something iced and caffeinated", matcha: "matcha vibes", "milk tea": "bubble tea" },
      milk: { "whole milk": "regular milk", "oat milk": "oat", "almond milk": "almond", none: "no dairy" },
      sweetness: { "no sugar": "zero sweet stuff", "light sugar": "not crazy sweet", "regular sugar": "a little sweet", "extra sweet": "super sweet" },
      topping: { boba: "boba", "coffee jelly": "coffee jelly", foam: "foam", none: "no toppings" },
      vibe: { classic: "classic", cozy: "chill", energetic: "high-energy", experimental: "something wild" },
    },
    negation: {
      base: { espresso: "espresso, not tea", "cold brew": "cold brew, not hot coffee", matcha: "matcha, not espresso", "milk tea": "milk tea, not coffee" },
      milk: { "whole milk": "whole milk, not plant milk", "oat milk": "oat milk, not dairy", "almond milk": "almond milk, not dairy", none: "no milk and no dairy" },
      sweetness: { "no sugar": "no sugar, not sweetened", "light sugar": "light sugar, not extra sweet", "regular sugar": "regular sugar, not unsweetened", "extra sweet": "extra sweet, not lightly sweetened" },
      topping: { boba: "boba, not jelly or foam", "coffee jelly": "coffee jelly, not boba or foam", foam: "foam, not boba or jelly", none: "no topping, not boba, jelly, or foam" },
      vibe: { classic: "classic, not experimental", cozy: "cozy, not high-energy", energetic: "energetic, not subdued", experimental: "experimental, not classic" },
    },
    multi_clue: {
      base: { espresso: "a bold espresso base", "cold brew": "a chilled cold-brew base", matcha: "a smooth matcha base", "milk tea": "a tea-forward milk-tea base" },
      milk: { "whole milk": "whole milk for a creamy finish", "oat milk": "oat milk for a smooth finish", "almond milk": "almond milk for a nutty finish", none: "no milk to keep it dairy-free" },
      sweetness: { "no sugar": "with no added sugar", "light sugar": "with just a little sweetness", "regular sugar": "with balanced sweetness", "extra sweet": "with extra sweetness" },
      topping: { boba: "finished with chewy boba", "coffee jelly": "finished with coffee jelly", foam: "topped with a soft foam", none: "with no topping" },
      vibe: { classic: "for a classic feel", cozy: "for a cozy feel", energetic: "for an energetic feel", experimental: "for an experimental feel" },
    },
  };

  const DIFFICULTY_TEMPLATES = {
    easy: ["Please make a {base} with {milk}, {sweetness}, and {topping}. Keep it {vibe}.", "I'd like {base}; use {milk}, {sweetness}, {topping}, and a {vibe} feel."],
    ambiguous: ["Could I get {base}, {milk}, {sweetness}, and {topping}, with {vibe} vibes?", "I'm in the mood for {base}; something {milk}, {sweetness}, {topping}, and {vibe}."],
    slang: ["Yo, get me {base}, {milk}, {sweetness}, {topping}, and keep it {vibe}.", "Bro, {base} with {milk}, {sweetness}, {topping}; make it {vibe}."],
    negation: ["I'm set on {base}; for the details: {milk}; {sweetness}; {topping}; and {vibe}.", "Please prepare {base}, and use these specifics: {milk}; {sweetness}; {topping}; {vibe}."],
    multi_clue: ["I'm after {base}, {milk}, {sweetness}, and {topping}; all together for a {vibe} drink.", "For the base, choose {base}; add {milk}, {sweetness}, {topping}, and finish {vibe}."],
  };

  function createSeededRandom(seed) {
    let value = seed >>> 0;
    return function () {
      value += 0x6d2b79f5;
      let mixed = value;
      mixed = Math.imul(mixed ^ (mixed >>> 15), mixed | 1);
      mixed ^= mixed + Math.imul(mixed ^ (mixed >>> 7), mixed | 61);
      return ((mixed ^ (mixed >>> 14)) >>> 0) / 4294967296;
    };
  }

  function pick(options, random) {
    return options[Math.floor(random() * options.length)];
  }

  function generateCustomerOrder(canonicalOrder, personaId, random = Math.random, difficulty = "normal", clearAttributes = []) {
    const persona = PERSONAS[personaId];
    if (!persona) {
      throw new Error(`Unknown BrewAI persona: ${personaId}`);
    }

    const recipe = { ...canonicalOrder };
    const missing = ["base", "milk", "sweetness", "topping", "vibe"].filter(
      (attribute) => !recipe[attribute],
    );
    if (missing.length) {
      throw new Error(`Canonical order is missing: ${missing.join(", ")}`);
    }

    const basePhrase = pick(BASE_WORDING[recipe.base] || [recipe.base], random);
    const preferredBase = persona.coffee_knowledge >= 0.9
      ? { espresso: "cortado-style espresso", "cold brew": "cold-brew coffee" }[recipe.base]
      : null;
    const wording = {
      ...recipe,
      base: preferredBase || basePhrase,
      milk: recipe.milk === "none" ? "no milk" : recipe.milk,
      topping: recipe.topping === "none" ? "no topping" : recipe.topping,
      opening: pick(persona.preferred_wording, random),
    };
    const difficultyMap = DIFFICULTY_WORDING[difficulty];
    if (difficultyMap) {
      ["base", "milk", "sweetness", "topping", "vibe"].forEach((attribute) => {
        if (!clearAttributes.includes(attribute)) {
          wording[attribute] = difficultyMap[attribute]?.[recipe[attribute]] || wording[attribute];
        }
      });
      const template = pick(DIFFICULTY_TEMPLATES[difficulty], random);
      return {
        request: `${wording.opening}: ${template.replace(/\{(\w+)\}/g, (_match, key) => wording[key] || "")}`,
        difficulty,
        persona: {
          id: persona.id,
          display_name: persona.display_name,
          character_label: persona.character_label,
          patience: persona.patience,
          verbosity: persona.verbosity,
          ambiguity: persona.ambiguity,
          coffee_knowledge: persona.coffee_knowledge,
          preferred_wording: persona.preferred_wording,
        },
      };
    }
    if (random() < persona.ambiguity) {
      wording.hedge = `${pick(OPTIONAL_HEDGES, random)} `;
    } else {
      wording.hedge = "";
    }

    const template = pick(persona.templates, random);
    let request = template.replace(/\{(\w+)\}/g, (_match, key) => wording[key] || "");
    if (persona.verbosity > 0.6 && random() < persona.verbosity) {
      request += ` ${pick(CONTEXT_LINES, random)}`;
    }
    if (wording.hedge) {
      request = `${wording.hedge}${request.charAt(0).toLowerCase()}${request.slice(1)}`;
    }

    return {
      request,
      difficulty: "normal",
      persona: {
        id: persona.id,
        display_name: persona.display_name,
        character_label: persona.character_label,
        patience: persona.patience,
        verbosity: persona.verbosity,
        ambiguity: persona.ambiguity,
        coffee_knowledge: persona.coffee_knowledge,
        preferred_wording: persona.preferred_wording,
      },
    };
  }

  function responseTimeForPatience(patience, baseSeconds = 30) {
    return Math.max(27, Math.min(33, Math.round(baseSeconds + (patience - 0.8) * 10)));
  }

  return {
    PERSONAS,
    createSeededRandom,
    generateCustomerOrder,
    responseTimeForPatience,
  };
});
