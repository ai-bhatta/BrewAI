const apiBaseUrl = "http://127.0.0.1:8000";
const { PERSONAS, createSeededRandom, generateCustomerOrder, responseTimeForPatience } = window.BrewAIPersonas;
const { createRushHourShift, recordRushHourCustomer, recordRushHourHint, recordRushHourClarification, recordRushHourDifficulty, isRushHourComplete, summarizeRushHour } = window.BrewAIRushHour;
const { CONFIG: clarificationConfig, getConfidenceStatus, selectClarificationAttribute, createClarificationReply, applyClarificationTimePenalty } = window.BrewAIClarification;
const { createHintState, selectHintTarget, advanceHint } = window.BrewAIHints;
const { createPerformanceState, recordOrder, summarizePerformance, evaluateDifficulty } = window.BrewAIDifficulty;
const { chooseNextDifficulty } = window.BrewAIBanditPolicy;
const RUSH_HOUR_CUSTOMERS = 5;

const builderOptions = {
  base: ["espresso", "cold brew", "matcha", "milk tea"],
  milk: ["whole milk", "oat milk", "almond milk", "none"],
  sweetness: ["no sugar", "light sugar", "regular sugar", "extra sweet"],
  topping: ["boba", "coffee jelly", "foam", "none"],
  vibe: ["classic", "cozy", "energetic", "experimental"],
};

const customerOrders = [
  { name: "Mina", recipe: { base: "espresso", milk: "whole milk", sweetness: "light sugar", topping: "boba", vibe: "cozy" } },
  { name: "Dev", recipe: { base: "cold brew", milk: "whole milk", sweetness: "extra sweet", topping: "foam", vibe: "experimental" } },
  { name: "Lina", recipe: { base: "milk tea", milk: "none", sweetness: "light sugar", topping: "none", vibe: "cozy" } },
  { name: "Omar", recipe: { base: "cold brew", milk: "whole milk", sweetness: "extra sweet", topping: "boba", vibe: "energetic" } },
  { name: "Sora", recipe: { base: "matcha", milk: "almond milk", sweetness: "regular sugar", topping: "foam", vibe: "experimental" } },
  { name: "Noah", recipe: { base: "espresso", milk: "none", sweetness: "no sugar", topping: "coffee jelly", vibe: "classic" } },
];

const drinkArtMap = {
  espresso: "../Espresso.png",
  "cold brew": "../cold_coffee.png",
  matcha: "../Matcha_latte.png",
  "milk tea": "../Bubble_tea.png",
};

const drinkDescriptionMap = {
  espresso: "A rich espresso profile tuned for bold coffee orders and fast, focused service runs.",
  "cold brew": "A chilled cafe build with a sharper energy, ideal for bright and rush-hour style requests.",
  matcha: "A glowing matcha presentation that suits playful or experimental tea-forward orders.",
  "milk tea": "A cozy bubble-tea presentation that works well for calm and comfort-driven customer moods.",
};

const fallbackKeywordRules = [
  { tokens: ["strong", "boldest", "coffee", "espresso"], effects: { base: "espresso" } },
  { tokens: ["iced", "cold", "energy", "high-energy", "energetic"], effects: { base: "cold brew", vibe: "energetic" } },
  { tokens: ["tea", "calm", "afternoon"], effects: { base: "milk tea", vibe: "cozy" } },
  { tokens: ["matcha"], effects: { base: "matcha" } },
  { tokens: ["creamy", "comforting", "cozy"], effects: { milk: "whole milk", vibe: "cozy" } },
  { tokens: ["no dairy", "dairy-free", "oat"], effects: { milk: "oat milk" } },
  { tokens: ["no milk", "without milk"], effects: { milk: "none" } },
  { tokens: ["almond"], effects: { milk: "almond milk" } },
  { tokens: ["not too sweet", "less sugar", "light"], effects: { sweetness: "light sugar" } },
  { tokens: ["no sugar", "unsweetened"], effects: { sweetness: "no sugar" } },
  { tokens: ["sweet", "playful"], effects: { sweetness: "regular sugar" } },
  { tokens: ["extra sweetness", "extra sweet"], effects: { sweetness: "extra sweet" } },
  { tokens: ["boba", "chewy"], effects: { topping: "boba" } },
  { tokens: ["jelly"], effects: { topping: "coffee jelly" } },
  { tokens: ["futuristic", "unusual", "experimental", "surprise"], effects: { vibe: "experimental" } },
];

const state = {
  score: 0,
  served: 0,
  confidence: null,
  currentCustomer: null,
  currentRecipe: {},
  inferredRecipe: {},
  groundTruthRecipe: {},
  currentInterpretation: null,
  parserSource: "loading",
  playerCount: 1,
  players: [],
  activePlayerIndex: 0,
  roundSeconds: 30,
  featureFlags: { timer_seconds: 30, hint_penalty: { "1": 1, "2": 2, "3": 3 }, clarification_time_penalty: 3, adaptive_difficulty: null, adaptive_policy: null },
  prefetchedCustomer: null,
  customerPrefetchToken: 0,
  timeLeft: 30,
  timerId: null,
  roundActive: false,
  matchStarted: false,
  mode: "game",
  random: createSeededRandom(Date.now()),
  rushHourShift: null,
  currentOrderStartedAt: null,
  currentOrderSeconds: 30,
  orderResolving: false,
  clarifiedAttributes: new Set(),
  gameEvents: [],
  hintState: createHintState(),
  difficultyState: createPerformanceState(),
  adaptiveDifficulty: true,
  adaptivePolicy: "heuristic",
  selectedDifficulty: "normal",
  hintsThisOrder: 0,
  clarificationsThisOrder: 0,
  roundOrdersAttempted: 0,
  roundOrdersCorrect: 0,
  roundStartedAt: null,
};

const overlayEl = document.getElementById("game-overlay");
const overlayTitleEl = document.getElementById("overlay-title");
const overlayDescriptionEl = document.getElementById("overlay-description");
const setupPanelEl = document.getElementById("setup-panel");
const turnPanelEl = document.getElementById("turn-panel");
const resultsPanelEl = document.getElementById("results-panel");
const singlePlayerBtn = document.getElementById("single-player-btn");
const twoPlayerBtn = document.getElementById("two-player-btn");
const gameModeBtn = document.getElementById("game-mode-btn");
const rushHourModeBtn = document.getElementById("rush-hour-mode-btn");
const playerOneNameInput = document.getElementById("player-one-name");
const playerTwoField = document.getElementById("player-two-field");
const playerTwoNameInput = document.getElementById("player-two-name");
const startGameBtn = document.getElementById("start-game-btn");
const adaptiveDifficultyToggle = document.getElementById("adaptive-difficulty-toggle");
const adaptiveDifficultyLabel = document.getElementById("adaptive-difficulty-label");
const adaptivePolicySelect = document.getElementById("adaptive-policy-select");
const selectedDifficultyEl = document.getElementById("selected-difficulty");
const beginTurnBtn = document.getElementById("begin-turn-btn");
const playAgainBtn = document.getElementById("play-again-btn");
const turnMessageEl = document.getElementById("turn-message");
const resultsSummaryEl = document.getElementById("results-summary");
const builderGroups = document.getElementById("builder-groups");
const currentRecipeEl = document.getElementById("current-recipe");
const customerNameEl = document.getElementById("customer-name");
const customerRequestEl = document.getElementById("customer-request");
const personaBadgeEl = document.getElementById("persona-badge");
const adaptivePolicyNoteEl = document.getElementById("adaptive-policy-note");
const aiSummaryPanelEl = document.getElementById("ai-summary-panel");
const summaryListEl = document.getElementById("ai-summary-list");
const feedbackMessageEl = document.getElementById("feedback-message");
const aiMetaEl = document.getElementById("ai-meta");
const hintHelperTextEl = document.getElementById("hint-helper-text");
const hintResultEl = document.getElementById("hint-result");
const uncertaintyPanelEl = document.getElementById("uncertainty-panel");
const uncertaintyMessageEl = document.getElementById("uncertainty-message");
const clarifyBtn = document.getElementById("clarify-btn");
const clarificationReplyEl = document.getElementById("clarification-reply");
const activePlayerEl = document.getElementById("active-player");
const timerEl = document.getElementById("round-timer");
const scoreEl = document.getElementById("score");
const servedCountEl = document.getElementById("served-count");
const shiftProgressCardEl = document.getElementById("shift-progress-card");
const shiftProgressEl = document.getElementById("shift-progress");
const confidenceEl = document.getElementById("confidence");
const scoreboardListEl = document.getElementById("scoreboard-list");
const matchLabelEl = document.getElementById("match-label");
const serveBtn = document.getElementById("serve-btn");
const hintButtons = [1, 2, 3].map((level) => document.getElementById(`hint-level-${level}-btn`));
const nextOrderBtn = document.getElementById("next-order-btn");
const statusDotEl = document.getElementById("status-dot");
const serviceStatusTextEl = document.getElementById("service-status-text");
const drinkPreviewImageEl = document.getElementById("drink-preview-image");
const drinkPreviewTitleEl = document.getElementById("drink-preview-title");
const drinkPreviewDescriptionEl = document.getElementById("drink-preview-description");

function toTitleCase(value) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function getActivePlayer() {
  return state.players[state.activePlayerIndex] || null;
}

function resetRoundStats(player) {
  player.score = 0;
  player.served = 0;
}

function syncStateFromPlayer() {
  const player = getActivePlayer();
  if (!player) {
    return;
  }
  state.score = player.score;
  state.served = player.served;
}

function lockGameplay(locked) {
  const panels = document.querySelectorAll(".game-grid .panel");
  panels.forEach((panel) => {
    panel.classList.toggle("disabled", locked);
  });

  serveBtn.disabled = locked;
  hintButtons.forEach((button) => { button.disabled = locked; });
  nextOrderBtn.disabled = locked;
  document.querySelectorAll(".builder-group select").forEach((select) => {
    select.disabled = locked;
  });
}

function setServiceStatus(mode) {
  statusDotEl.className = "status-dot";

  if (mode === "online") {
    statusDotEl.classList.add("ok");
    serviceStatusTextEl.textContent = "AI backend online";
    return;
  }

  if (mode === "offline") {
    statusDotEl.classList.add("offline");
    serviceStatusTextEl.textContent = "Backend offline, using fallback parser";
    return;
  }

  if (mode === "fallback") {
    statusDotEl.classList.add("offline");
    serviceStatusTextEl.textContent = "Backend online, keyword parser active";
    return;
  }

  serviceStatusTextEl.textContent = "Checking AI backend...";
}

function buildSelectors() {
  Object.entries(builderOptions).forEach(([group, options]) => {
    const wrapper = document.createElement("div");
    wrapper.className = "builder-group";

    const label = document.createElement("label");
    label.setAttribute("for", group);
    label.textContent = toTitleCase(group);

    const select = document.createElement("select");
    select.id = group;
    select.name = group;

    options.forEach((option) => {
      const optionEl = document.createElement("option");
      optionEl.value = option;
      optionEl.textContent = toTitleCase(option);
      select.appendChild(optionEl);
    });

      select.addEventListener("change", () => {
      if (!state.roundActive) {
        return;
      }
      state.currentRecipe[group] = select.value;
      renderCurrentRecipe();
    });

    wrapper.append(label, select);
    builderGroups.appendChild(wrapper);
    state.currentRecipe[group] = options[0];
  });
}

function fallbackInterpretation(orderText) {
  const normalized = orderText.toLowerCase();
  const inferred = {
    base: "espresso",
    milk: "whole milk",
    sweetness: "regular sugar",
    topping: "none",
    vibe: "classic",
  };

  fallbackKeywordRules.forEach((rule) => {
    if (rule.tokens.some((token) => normalized.includes(token))) {
      Object.assign(inferred, rule.effects);
    }
  });

  return {
    recipe: inferred,
    confidence: Object.fromEntries(Object.keys(builderOptions).map((key) => [key, null])),
    source: "heuristic-fallback",
    explanation: [
      "Backend model unavailable",
      "Applied keyword rules to keep the game playable",
    ],
  };
}

async function checkBackend() {
  try {
    const response = await fetch(`${apiBaseUrl}/api/health`);
    if (!response.ok) {
      throw new Error("health-check-failed");
    }
    const health = await response.json();
    setServiceStatus(health.model_loaded ? "online" : "fallback");
  } catch (error) {
    setServiceStatus("offline");
  }
}

function recordGameEvent(type, details = {}) {
  state.gameEvents.push({ type, ...details, order: state.rushHourShift?.completedCustomers || 0 });
  if (["hint_requested", "clarification_requested", "difficulty_evaluated", "difficulty_changed"].includes(type)) {
    window.BrewAIAnalytics?.track(type, {
      ...details,
      difficulty: state.currentCustomer?.difficulty || state.difficultyState.difficulty,
    }, state.activePlayerIndex, state.mode);
  }
}

async function applyDifficultyOutcome(accuracy, responseTimeSeconds, mistakeAttributes, customerLost = false) {
  const player = getActivePlayer();
  const current = player?.difficultyState || state.difficultyState;
  const updated = recordOrder(current, {
    accuracy,
    responseTimeSeconds,
    hintsUsed: state.hintsThisOrder,
    clarificationsUsed: state.clarificationsThisOrder,
    correct: accuracy >= 1,
    mistakeAttributes,
  });
  const { state: nextState, decision } = evaluateDifficulty(updated, {
    adaptiveEnabled: state.adaptiveDifficulty,
    fixedDifficulty: state.selectedDifficulty,
  });
  state.difficultyState = nextState;
  if (player) player.difficultyState = nextState;

  recordGameEvent("difficulty_evaluated", {
    previous_difficulty: decision.previous,
    new_difficulty: decision.next,
    difficulty_reason: decision.reason,
    metrics: decision.metrics,
  });
  if (decision.changed) {
    recordGameEvent("difficulty_changed", {
      previous_difficulty: decision.previous,
      new_difficulty: decision.next,
      difficulty_reason: decision.reason,
    });
  }
  if (state.rushHourShift) {
    state.rushHourShift = recordRushHourDifficulty(state.rushHourShift, decision.next);
  }
  if (state.adaptivePolicy === "contextual_bandit" && player?.pendingBanditDecision) {
    const pending = player.pendingBanditDecision;
    player.pendingBanditDecision = null;
    try {
      const response = await fetch(`${apiBaseUrl}/api/bandit/outcome`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
          signal: AbortSignal.timeout(1200),
        body: JSON.stringify({ decision_id: pending.decision_id, correct: accuracy >= 1,
          customer_lost: customerLost, response_time_seconds: responseTimeSeconds,
          hints_used: state.hintsThisOrder, clarifications_used: state.clarificationsThisOrder }),
      });
      if (!response.ok) throw new Error("Bandit outcome update failed");
      const result = await response.json();
      if (result.updated) window.BrewAIAnalytics?.track("adaptive_policy_outcome", {
        policy: "contextual_bandit", action: pending.chosen_difficulty,
        difficulty: pending.chosen_difficulty, reward: result.reward,
        correct: accuracy >= 1, customer_lost: customerLost,
        response_time_seconds: responseTimeSeconds,
      }, state.activePlayerIndex, state.mode);
    } catch (_error) {
      window.BrewAIAnalytics?.track("adaptive_policy_update_failed", {}, state.activePlayerIndex, state.mode);
    }
  }
  return decision;
}

function renderUncertainty() {
  const confidences = state.currentInterpretation?.confidence;
  const attribute = selectClarificationAttribute(confidences, state.clarifiedAttributes);
  if (!state.roundActive) {
    uncertaintyPanelEl.classList.add("hidden");
    return;
  }
  if (!attribute) {
    clarifyBtn.classList.add("hidden");
    if (clarificationReplyEl.classList.contains("hidden")) {
      uncertaintyPanelEl.classList.add("hidden");
    } else {
      uncertaintyPanelEl.classList.remove("hidden");
      uncertaintyMessageEl.textContent = "No other uncertain attributes to clarify.";
    }
    return;
  }
  clarifyBtn.classList.remove("hidden");
  const confidence = confidences[attribute];
  uncertaintyPanelEl.classList.remove("hidden");
  uncertaintyMessageEl.textContent = `AI uncertain about: ${toTitleCase(attribute)} (${Math.round(confidence * 100)}%, ${getConfidenceStatus(confidence).replace("-", " ")}).`;
  clarifyBtn.disabled = state.orderResolving;
}

function updateHintControls() {
  const levels = state.hintState.levelsByAttribute;
  const target = state.hintState.currentAttribute || selectHintTarget(
    state.currentInterpretation?.confidence,
    levels,
  );
  const currentLevel = target ? levels[target] || 0 : 3;
  hintButtons.forEach((button, index) => {
    button.disabled = !state.roundActive || !target || index + 1 !== currentLevel + 1;
  });
  const nextHint = ["Nudge (-1)", "Strong hint (-2)", "Reveal (-3)"][currentLevel];
  hintHelperTextEl.textContent = target
    ? `Need help with ${toTitleCase(target)}? Next: ${nextHint}. Asking the customer costs 3 seconds.`
    : "You have all the clues for this order.";
}

function askForClarification() {
  if (!state.roundActive || state.orderResolving) return;
  const attribute = selectClarificationAttribute(
    state.currentInterpretation?.confidence,
    state.clarifiedAttributes,
  );
  if (!attribute) return;
  const reply = createClarificationReply(attribute, state.groundTruthRecipe);
  if (!reply) return;

  recordGameEvent("clarification_attribute", { attribute });
  state.clarifiedAttributes.add(attribute);
  clarificationReplyEl.textContent = `Customer: "${reply}"`;
  clarificationReplyEl.classList.remove("hidden");
  const before = state.timeLeft;
  state.timeLeft = applyClarificationTimePenalty(
    state.timeLeft,
    state.featureFlags.clarification_time_penalty ?? clarificationConfig.CLARIFICATION_TIME_PENALTY_SECONDS,
  );
  recordGameEvent("clarification_requested", {
    attribute,
    time_penalty: before - state.timeLeft,
    difficulty: state.currentCustomer?.difficulty || state.difficultyState.difficulty,
  });
  recordGameEvent("clarification_time_penalty", {
    seconds: before - state.timeLeft,
    configuredSeconds: clarificationConfig.CLARIFICATION_TIME_PENALTY_SECONDS,
  });
  if (state.mode === "rush_hour") {
    state.rushHourShift = recordRushHourClarification(state.rushHourShift);
  }
  state.clarificationsThisOrder += 1;
  renderUncertainty();
  updateStats();
  feedbackMessageEl.textContent = `Customer clarified ${attribute}. You lost ${before - state.timeLeft} seconds.`;
  if (state.timeLeft <= 0) {
    if (state.mode === "rush_hour") void completeRushHourCustomer("lost", 0);
    else void finishTurn();
  }
}

function hideHintPanel() {
  aiSummaryPanelEl.classList.add("hidden");
  hintHelperTextEl.classList.remove("hidden");
  summaryListEl.innerHTML = "";
  aiMetaEl.textContent = "";
  state.confidence = null;
  updateStats();
}

function renderCurrentRecipe() {
  currentRecipeEl.innerHTML = "";

  Object.entries(state.currentRecipe).forEach(([key, value]) => {
    const pill = document.createElement("span");
    pill.className = "tag";
    pill.textContent = `${toTitleCase(key)}: ${toTitleCase(value)}`;
    currentRecipeEl.appendChild(pill);
  });

  updateDrinkPreview();
}

function syncSelectors() {
  Object.entries(state.currentRecipe).forEach(([group, value]) => {
    const select = document.getElementById(group);
    if (select) {
      select.value = value;
    }
  });
}

function randomCustomer() {
  const previousRequest = state.currentCustomer?.request;
  let generatedCustomer;
  for (let attempt = 0; attempt < 6; attempt += 1) {
    const customer = customerOrders[Math.floor(state.random() * customerOrders.length)];
    const personaIds = Object.keys(PERSONAS);
    const personaId = personaIds[Math.floor(state.random() * personaIds.length)];
    const difficulty = state.difficultyState.difficulty;
    const clearAttributes = summarizePerformance(state.difficultyState).recentMistakeAttributes;
    const generated = generateCustomerOrder(
      customer.recipe,
      personaId,
      state.random,
      difficulty,
      clearAttributes,
    );
    generatedCustomer = { ...customer, ...generated, generationSource: "template" };
    if (generatedCustomer.request !== previousRequest) {
      break;
    }
  }
  return generatedCustomer;
}

async function prefetchNextCustomer() {
  if (!state.roundActive || !state.currentCustomer) return;
  const token = ++state.customerPrefetchToken;
  const currentCustomer = state.currentCustomer;
  const candidate = randomCustomer();
  try {
    const generated = await window.BrewAICustomerGeneration.generate(candidate, "game");
    if (!state.roundActive || token !== state.customerPrefetchToken || state.currentCustomer !== currentCustomer) return;
    state.prefetchedCustomer = { ...candidate, request: generated.request, generationSource: generated.source, generationTelemetryRecorded: true };
  } catch (_error) {
    if (state.roundActive && token === state.customerPrefetchToken && state.currentCustomer === currentCustomer) {
      state.prefetchedCustomer = candidate;
    }
  }
}

function randomOption(group, exceptValue) {
  const options = builderOptions[group].filter((option) => option !== exceptValue);
  const pool = options.length ? options : builderOptions[group];
  return pool[Math.floor(state.random() * pool.length)];
}

function createRandomRecipe(targetRecipe) {
  const recipe = {};

  Object.keys(builderOptions).forEach((group) => {
    recipe[group] = randomOption(group);
  });

  const allMatched = Object.keys(targetRecipe).every(
    (group) => recipe[group] === targetRecipe[group],
  );

  if (allMatched) {
    const groupNames = Object.keys(builderOptions);
    const forcedGroup = groupNames[Math.floor(state.random() * groupNames.length)];
    recipe[forcedGroup] = randomOption(forcedGroup, targetRecipe[forcedGroup]);
  }

  return recipe;
}

async function interpretCurrentOrder(customer) {
  try {
    const response = await fetch(`${apiBaseUrl}/api/order/interpret`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        customer_name: customer.name,
        request: customer.request,
        persona: customer.persona.id,
        display_name: customer.persona.display_name,
        character_label: customer.persona.character_label,
        patience: customer.persona.patience,
        verbosity: customer.persona.verbosity,
        ambiguity: customer.persona.ambiguity,
        coffee_knowledge: customer.persona.coffee_knowledge,
        preferred_wording: customer.persona.preferred_wording,
      }),
    });

    if (!response.ok) {
      throw new Error("interpret-failed");
    }

    const result = await response.json();
    state.parserSource = result.source;
    setServiceStatus("online");
    return result;
  } catch (error) {
    setServiceStatus("offline");
    return fallbackInterpretation(customer.request);
  }
}

async function loadOrder() {
  if (!state.roundActive) {
    return;
  }

  state.orderResolving = true;
  const previousCustomer = state.currentCustomer;
  const prefetchedCustomer = state.prefetchedCustomer;
  state.prefetchedCustomer = null;
  state.customerPrefetchToken += 1;
  if (previousCustomer && state.adaptiveDifficulty && state.adaptivePolicy === "contextual_bandit") {
    const player = getActivePlayer();
    const sessionId = window.BrewAIAnalytics?.getSessionId();
    if (player && sessionId) {
      const metrics = summarizePerformance(state.difficultyState);
      const selection = await chooseNextDifficulty(previousCustomer.difficulty, state.difficultyState.difficulty, async () => {
        const response = await fetch(`${apiBaseUrl}/api/bandit/decision`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          signal: AbortSignal.timeout(1200),
          body: JSON.stringify({
            session_id: sessionId,
            player_id: `${sessionId}_p${state.activePlayerIndex + 1}`,
            current_difficulty: previousCustomer.difficulty,
            heuristic_action: state.difficultyState.difficulty,
            metrics: {
              recentAccuracy: metrics.recentAccuracy,
              averageResponseTime: metrics.averageResponseTime,
              hintOrderRatio: metrics.hintOrderRatio,
              clarificationOrderRatio: metrics.clarificationOrderRatio,
              currentStreak: state.difficultyState.currentStreak,
            },
          }),
        });
        if (!response.ok) throw new Error("Bandit decision unavailable");
        return response.json();
      });
      state.difficultyState = { ...state.difficultyState, difficulty: selection.difficulty };
      player.difficultyState = state.difficultyState;
      player.pendingBanditDecision = selection.decision;
      if (selection.decision) {
        const result = selection.decision;
        adaptivePolicyNoteEl.textContent = `Contextual bandit | ${result.mode.replaceAll("_", " ")} | ${result.reason.replaceAll("_", " ")} | estimated reward ${result.estimated_reward.toFixed(2)}. This is a policy estimate, not a causal explanation.`;
        window.BrewAIAnalytics?.track("adaptive_policy_decision", {
          policy: result.policy, mode: result.mode, action: result.chosen_difficulty,
          current_difficulty: previousCustomer.difficulty,
          estimated_reward: result.estimated_reward, reason: result.reason,
        }, state.activePlayerIndex, state.mode);
      } else {
        adaptivePolicyNoteEl.textContent = "Bandit service unavailable; using the heuristic difficulty choice.";
      }
    }
  } else if (state.adaptiveDifficulty) {
    adaptivePolicyNoteEl.textContent = state.adaptivePolicy === "heuristic"
      ? "Heuristic baseline: uses recent accuracy, response speed, hints, clarification, and streaks."
      : "Contextual bandit starts adapting after the first completed order.";
  } else {
    adaptivePolicyNoteEl.textContent = `Fixed difficulty: ${state.selectedDifficulty}.`;
  }
  const customer = prefetchedCustomer && prefetchedCustomer.difficulty === state.difficultyState.difficulty
    ? prefetchedCustomer
    : randomCustomer();
  state.currentCustomer = customer;

  customerNameEl.textContent = customer.name;
  customerRequestEl.textContent = `"${customer.request}"`;
  personaBadgeEl.textContent = `${customer.persona.display_name} | ${customer.persona.character_label} | ${toTitleCase(customer.difficulty)} | ${customer.generationSource === "local_ai" ? "Generated locally" : "Template"}`;
  personaBadgeEl.classList.remove("hidden");
  hintButtons.forEach((button) => { button.disabled = true; });
  state.hintState = createHintState();
  state.hintsThisOrder = 0;
  state.clarificationsThisOrder = 0;
  hintResultEl.textContent = "";
  hintResultEl.classList.add("hidden");
  state.clarifiedAttributes = new Set();
  clarificationReplyEl.textContent = "";
  clarificationReplyEl.classList.add("hidden");
  uncertaintyPanelEl.classList.add("hidden");
  hideHintPanel();

  const interpretation = await interpretCurrentOrder(customer);

  state.currentInterpretation = interpretation;
  if (!state.roundActive) {
    state.orderResolving = false;
    return;
  }
  state.inferredRecipe = interpretation.recipe;
  state.groundTruthRecipe = customer.recipe;
  const confidenceValues = Object.values(interpretation?.confidence || {});
  if ((state.mode === "rush_hour" ? state.rushHourShift?.completedCustomers : state.roundOrdersAttempted) > 0) {
    window.BrewAIAnalytics?.track("next_round", {
      difficulty: customer.difficulty,
      game_mode: state.mode,
    }, state.activePlayerIndex, state.mode);
  }
  window.BrewAIAnalytics?.track("customer_received", {
    difficulty: customer.difficulty,
    persona: customer.persona.id,
    generation_source: customer.generationSource || "template",
    confidence_available: confidenceValues.some((value) => typeof value === "number"),
    model_source: interpretation?.source || "unknown",
  }, state.activePlayerIndex, state.mode);
  state.currentRecipe = createRandomRecipe(customer.recipe);
  state.confidence = null;
  const availableAttribute = selectClarificationAttribute(interpretation?.confidence);
  if (availableAttribute) recordGameEvent("clarification_available", { attribute: availableAttribute });
  state.hintState.currentAttribute = selectHintTarget(
    interpretation?.confidence,
    state.hintState.levelsByAttribute,
  );

  syncSelectors();
  renderCurrentRecipe();
  state.orderResolving = false;
  updateHintControls();
  renderUncertainty();
  if (state.mode === "rush_hour") {
    state.currentOrderSeconds = responseTimeForPatience(customer.persona.patience);
    state.timeLeft = state.currentOrderSeconds;
    startOrderClock(state.currentOrderSeconds);
  } else {
    state.currentOrderStartedAt = performance.now();
  }
  if (!customer.generationTelemetryRecorded) {
    window.BrewAIAnalytics?.track("generation_source", {
      source: customer.generationSource || "template", context: "game",
    }, state.activePlayerIndex, state.mode);
  }
  void prefetchNextCustomer();
  updateStats();
}

function startOrderClock(seconds) {
  clearInterval(state.timerId);
  state.timeLeft = seconds;
  state.currentOrderSeconds = seconds;
  state.currentOrderStartedAt = performance.now();
  state.timerId = window.setInterval(() => {
    state.timeLeft -= 1;
    updateStats();
    if (state.timeLeft <= 0) {
      void completeRushHourCustomer("lost", 0);
    }
  }, 1000);
}

function updateStats() {
  const activePlayer = getActivePlayer();
  activePlayerEl.textContent = activePlayer ? activePlayer.name : "Waiting";
  timerEl.textContent = `${state.timeLeft}s`;
  scoreEl.textContent = String(state.score);
  servedCountEl.textContent = String(state.served);
  shiftProgressCardEl.classList.toggle("hidden", state.mode !== "rush_hour");
  shiftProgressEl.textContent = state.rushHourShift
    ? `${state.rushHourShift.completedCustomers} / ${state.rushHourShift.totalCustomers}`
    : `0 / ${RUSH_HOUR_CUSTOMERS}`;
  confidenceEl.textContent = state.confidence == null
    ? "--"
    : `${Math.round(state.confidence * 100)}%`;
  renderScoreboard();
}

function buildPreviewTitle(recipe) {
  const baseLabel = toTitleCase(recipe.base || "signature");
  const vibeLabel = toTitleCase(recipe.vibe || "classic");
  return `${vibeLabel} ${baseLabel}`;
}

function updateDrinkPreview() {
  const base = state.currentRecipe.base || "espresso";
  const previewImage = drinkArtMap[base] || "../Pixel_Art_boba.png";
  const previewDescription = drinkDescriptionMap[base] || drinkDescriptionMap.espresso;
  const milk = state.currentRecipe.milk || "whole milk";
  const topping = state.currentRecipe.topping || "none";

  drinkPreviewImageEl.src = previewImage;
  drinkPreviewTitleEl.textContent = buildPreviewTitle(state.currentRecipe);
  drinkPreviewDescriptionEl.textContent =
    `${previewDescription} Built with ${milk} and ${topping}.`;
}

function renderScoreboard() {
  scoreboardListEl.innerHTML = "";

  if (!state.players.length) {
    const empty = document.createElement("p");
    empty.textContent = "Start a match to see the barista scoreboard.";
    scoreboardListEl.appendChild(empty);
    return;
  }

  state.players.forEach((player, index) => {
    const row = document.createElement("div");
    row.className = "scoreboard-row";
    if (index === state.activePlayerIndex && state.roundActive) {
      row.classList.add("active");
    }

    row.innerHTML = `
      <div class="scoreboard-name">${player.name}</div>
      <div class="scoreboard-metric"><span>Score</span><strong>${player.score}</strong></div>
      <div class="scoreboard-metric"><span>Served</span><strong>${player.served}</strong></div>
    `;
    scoreboardListEl.appendChild(row);
  });
}

function setOverlayMode(mode) {
  setupPanelEl.classList.toggle("hidden", mode !== "setup");
  turnPanelEl.classList.toggle("hidden", mode !== "turn");
  resultsPanelEl.classList.toggle("hidden", mode !== "results");
  overlayEl.classList.toggle("hidden", mode === "hidden");
}

function setPlayerMode(playerCount) {
  state.playerCount = playerCount;
  singlePlayerBtn.classList.toggle("active", playerCount === 1);
  twoPlayerBtn.classList.toggle("active", playerCount === 2);
  playerTwoField.classList.toggle("hidden", playerCount !== 2);
}

function setGameMode(mode) {
  state.mode = mode;
  window.BrewAIGameMode = mode;
  gameModeBtn.classList.toggle("active", mode === "game");
  rushHourModeBtn.classList.toggle("active", mode === "rush_hour");
  nextOrderBtn.textContent = mode === "rush_hour" ? "Lose Customer" : "Skip Order";
  matchLabelEl.textContent = mode === "rush_hour" ? "Rush Hour selected" : "Game Mode selected";
  updateStats();
}

function buildPlayersFromInputs() {
  const playerOneName = playerOneNameInput.value.trim() || "Player 1";
  const playerTwoName = playerTwoNameInput.value.trim() || "Player 2";

  if (state.playerCount === 1) {
    return [{ name: playerOneName, score: 0, served: 0 }];
  }

  return [
    { name: playerOneName, score: 0, served: 0 },
    { name: playerTwoName, score: 0, served: 0 },
  ];
}

function startMatchSetup() {
  state.featureFlags = window.BrewAIAnalytics?.getFeatureFlags() || state.featureFlags;
  state.roundSeconds = Number(state.featureFlags.timer_seconds) || 30;
  const assignedAdaptiveDifficulty = state.featureFlags.adaptive_difficulty;
  state.adaptiveDifficulty = typeof assignedAdaptiveDifficulty === "boolean"
    ? assignedAdaptiveDifficulty
    : adaptiveDifficultyToggle.checked;
  state.adaptivePolicy = ["heuristic", "contextual_bandit"].includes(state.featureFlags.adaptive_policy)
    ? state.featureFlags.adaptive_policy
    : adaptivePolicySelect.value;
  adaptiveDifficultyToggle.checked = state.adaptiveDifficulty;
  adaptiveDifficultyToggle.disabled = typeof assignedAdaptiveDifficulty === "boolean";
  adaptivePolicySelect.value = state.adaptivePolicy;
  adaptivePolicySelect.disabled = !state.adaptiveDifficulty || Boolean(state.featureFlags.adaptive_policy);
  adaptiveDifficultyLabel.textContent = `Adaptive Difficulty: ${state.adaptiveDifficulty ? "ON" : "OFF"}${adaptiveDifficultyToggle.disabled ? " (experiment)" : ""}`;
  state.random = createSeededRandom(Date.now());
  state.selectedDifficulty = selectedDifficultyEl.value;
  state.players = buildPlayersFromInputs();
  state.players.forEach((player) => {
    player.difficultyState = createPerformanceState(state.selectedDifficulty);
  });
  state.activePlayerIndex = 0;
  state.matchStarted = true;
  state.timeLeft = state.roundSeconds;
  state.confidence = null;
  state.currentCustomer = null;
  state.inferredRecipe = {};
  state.groundTruthRecipe = {};
  state.currentRecipe = {};
  state.rushHourShift = null;
  state.orderResolving = false;
  state.clarifiedAttributes = new Set();
  state.gameEvents = [];
  window.BrewAIAnalytics?.track("game_started", {
    player_count: state.players.length,
    difficulty: state.selectedDifficulty,
    adaptive_difficulty: state.adaptiveDifficulty,
    adaptive_policy: state.adaptivePolicy,
    timer_seconds: state.roundSeconds,
  }, null, state.mode);
  state.players.forEach((player) => {
    resetRoundStats(player);
    player.shiftSummary = null;
  });

  syncStateFromPlayer();
  matchLabelEl.textContent = state.mode === "rush_hour"
    ? `Rush Hour · Turn 1 of ${state.players.length}`
    : state.players.length === 1 ? "Single player round" : "Turn 1 of 2";
  feedbackMessageEl.textContent =
    "Read the rules, then begin the timed round. Balance accuracy, speed, and progressive hint costs.";
  setOverlayForTurnStart();
  updateStats();
}

function setOverlayForTurnStart() {
  const player = getActivePlayer();
  overlayTitleEl.textContent = state.players.length === 1 ? "Ready to Brew?" : `Pass to ${player.name}`;
  if (state.mode === "rush_hour") {
    overlayDescriptionEl.textContent =
      `Serve five customers before their individual patience timers expire. Each persona changes the timer slightly. Hints cost points; asking for clarification costs ${state.featureFlags.clarification_time_penalty ?? 3} seconds.`;
    turnMessageEl.textContent = `${player.name}, your Rush Hour shift has ${RUSH_HOUR_CUSTOMERS} customers. Serve each one or they will be lost.`;
  } else {
    overlayDescriptionEl.textContent =
      `Once you press Begin Turn, the timer starts immediately. Serve the requested drinks correctly within ${state.roundSeconds} seconds. Progressive hints cost points; asking the customer to clarify costs ${state.featureFlags.clarification_time_penalty ?? 3} seconds.`;
    turnMessageEl.textContent =
      `${player.name}, you have ${state.roundSeconds} seconds to build and serve as many accurate drinks as possible.`;
  }
  setOverlayMode("turn");
}

function startTurn() {
  const player = getActivePlayer();
  if (!player) {
    return;
  }

  resetRoundStats(player);
  state.difficultyState = player.difficultyState || createPerformanceState(state.selectedDifficulty);
  state.currentCustomer = null;
  syncStateFromPlayer();
  state.rushHourShift = state.mode === "rush_hour"
    ? createRushHourShift(RUSH_HOUR_CUSTOMERS, state.difficultyState.difficulty)
    : null;
  state.timeLeft = state.roundSeconds;
  state.roundActive = true;
  state.roundOrdersAttempted = 0;
  state.roundOrdersCorrect = 0;
  state.roundStartedAt = performance.now();
  window.BrewAIAnalytics?.track("round_started", {
    difficulty: state.difficultyState.difficulty,
    round_number: state.activePlayerIndex + 1,
  }, state.activePlayerIndex, state.mode);
  matchLabelEl.textContent = state.mode === "rush_hour"
    ? `${player.name}'s Rush Hour shift`
    : state.players.length === 1 ? `${player.name}'s timed round` : `${player.name}'s turn`;
  setOverlayMode("hidden");
  lockGameplay(false);
  updateStats();
  clearInterval(state.timerId);
  if (state.mode === "rush_hour") {
    loadOrder();
  } else {
    loadOrder();
    state.timerId = window.setInterval(() => {
      state.timeLeft -= 1;
      updateStats();

      if (state.timeLeft <= 0) {
        if (!state.orderResolving) void finishTurn();
      }
    }, 1000);
  }
}

async function finishTurn() {
  clearInterval(state.timerId);
  state.timerId = null;
  const player = getActivePlayer();
  if (state.mode === "game" && state.timeLeft <= 0 && state.currentCustomer && !state.orderResolving) {
    const elapsed = state.currentOrderStartedAt == null ? 0 : Math.max(0, (performance.now() - state.currentOrderStartedAt) / 1000);
    state.roundOrdersAttempted += 1;
    window.BrewAIAnalytics?.track("order_failed", {
      difficulty: state.currentCustomer.difficulty, failure_type: "lost",
      response_time_seconds: elapsed, hints_used: state.hintsThisOrder,
      clarifications_used: state.clarificationsThisOrder,
    }, state.activePlayerIndex, state.mode);
    if (player?.pendingBanditDecision) {
      state.orderResolving = true;
      await applyDifficultyOutcome(0, elapsed, Object.keys(state.groundTruthRecipe), true);
    }
  }
  state.roundActive = false;
  state.orderResolving = false;
  state.currentOrderStartedAt = null;
  lockGameplay(true);

  const roundDuration = state.roundStartedAt == null
    ? 0
    : Math.max(0, (performance.now() - state.roundStartedAt) / 1000);
  const roundEvent = state.roundOrdersAttempted === 0 && state.mode === "game"
    ? "round_failed"
    : "round_completed";
  window.BrewAIAnalytics?.track(roundEvent, roundEvent === "round_completed" ? {
    difficulty: state.difficultyState.difficulty,
    score: state.score,
    orders_attempted: state.roundOrdersAttempted,
    orders_correct: state.roundOrdersCorrect,
    customers_lost: state.rushHourShift?.customersLost || 0,
    duration_seconds: roundDuration,
  } : {
    difficulty: state.difficultyState.difficulty,
    failure_type: "no_orders_attempted",
    orders_attempted: state.roundOrdersAttempted,
    duration_seconds: roundDuration,
  }, state.activePlayerIndex, state.mode);
  state.roundStartedAt = null;
  if (player) {
    player.score = state.score;
    player.served = state.served;
    if (state.rushHourShift) {
      player.shiftSummary = summarizeRushHour(state.rushHourShift);
    }
  }

  if (state.activePlayerIndex < state.players.length - 1) {
    state.activePlayerIndex += 1;
    state.timeLeft = state.roundSeconds;
    state.score = 0;
    state.served = 0;
    state.confidence = null;
    state.rushHourShift = null;
    matchLabelEl.textContent = state.mode === "rush_hour"
      ? `Rush Hour - Turn ${state.activePlayerIndex + 1} of ${state.players.length}`
      : `Turn ${state.activePlayerIndex + 1} of ${state.players.length}`;
    feedbackMessageEl.textContent =
      `${player.name}'s turn is over. Pass the screen to the next barista.`;
    setOverlayForTurnStart();
    updateStats();
    return;
  }

  showResults();
}

function showResults() {
  const ranked = [...state.players].sort((left, right) => right.score - left.score);
  const bestScore = ranked[0].score;
  const winners = ranked.filter((player) => player.score === bestScore);
  const winnerText =
    winners.length === 1
      ? `${winners[0].name} wins the match with ${winners[0].score} points.`
      : `It's a tie at ${bestScore} points between ${winners.map((player) => player.name).join(" and ")}.`;

  overlayTitleEl.textContent = state.mode === "rush_hour" ? "SHIFT COMPLETE" : "Round Complete";
  overlayDescriptionEl.textContent = state.mode === "rush_hour" && state.players.length === 1
    ? `Your shift is complete. Final score: ${ranked[0].score}.`
    : winnerText;
  resultsSummaryEl.innerHTML = "";

  ranked.forEach((player) => {
    const row = document.createElement("div");
    row.className = state.mode === "rush_hour" ? "result-row shift-result" : "result-row";
    if (player.score === bestScore) {
      row.classList.add("winner-row");
    }
    const name = document.createElement("strong");
    name.textContent = player.name;
    row.appendChild(name);
    if (state.mode === "rush_hour") {
      const summary = player.shiftSummary || summarizeRushHour(createRushHourShift());
      const details = [
        `Score: ${summary.totalScore}`,
        `Customers served: ${summary.customersServed}/${summary.totalCustomers}`,
        `Correct orders: ${summary.correctDrinks}`,
        `Incorrect drinks: ${summary.incorrectDrinks}`,
        `Customers lost: ${summary.customersLost}`,
        `Hints used: ${summary.hintsUsed}`,
        `Hint penalty: -${summary.hintPointsSpent}`,
        `Clarifications used: ${summary.clarificationsUsed}`,
        `Difficulty: ${toTitleCase(summary.startingDifficulty)} -> ${toTitleCase(summary.endingDifficulty)} (${summary.difficultyChanges} changes)`,
        `Average response time: ${summary.averageResponseTimeSeconds.toFixed(1)}s`,
      ];
      details.forEach((detail) => {
        const metric = document.createElement("span");
        metric.textContent = detail;
        row.appendChild(metric);
      });
    } else {
      const result = document.createElement("span");
      result.textContent = `${player.score} pts | ${player.served} served`;
      row.appendChild(result);
    }
    resultsSummaryEl.appendChild(row);
  });

  feedbackMessageEl.textContent = state.mode === "rush_hour"
    ? "Rush Hour shift complete. Review the end-of-shift statistics."
    : winnerText;
  matchLabelEl.textContent = "Match finished";
  setOverlayMode("results");
  updateStats();
}

function resetToSetup() {
  clearInterval(state.timerId);
  state.timerId = null;
  state.score = 0;
  state.served = 0;
  state.confidence = null;
  state.currentCustomer = null;
  state.currentRecipe = {};
  state.inferredRecipe = {};
  state.groundTruthRecipe = {};
  state.currentInterpretation = null;
  state.hintState = createHintState();
  state.rushHourShift = null;
  state.currentOrderStartedAt = null;
  state.orderResolving = false;
  state.players = [];
  state.clarifiedAttributes = new Set();
  state.gameEvents = [];
  state.activePlayerIndex = 0;
  state.timeLeft = state.roundSeconds;
  state.roundActive = false;
  state.matchStarted = false;
  customerNameEl.textContent = "";
  customerRequestEl.textContent = "";
  personaBadgeEl.textContent = "";
  personaBadgeEl.classList.add("hidden");
  summaryListEl.innerHTML = "";
  aiMetaEl.textContent = "";
  aiSummaryPanelEl.classList.add("hidden");
  uncertaintyPanelEl.classList.add("hidden");
  hintHelperTextEl.classList.remove("hidden");
  currentRecipeEl.innerHTML = "";
  feedbackMessageEl.textContent = state.mode === "rush_hour"
    ? "Choose your players, then serve five customers in your Rush Hour shift."
    : `Choose your players, press start, and race to serve the most accurate drinks in ${state.roundSeconds} seconds.`;
  overlayTitleEl.textContent = "AI Barista Challenge";
  overlayDescriptionEl.textContent = state.mode === "rush_hour"
    ? `Rush Hour is a five-customer shift. Each persona has a slightly different response timer. Serve or lose each customer; hints cost points and clarification costs ${state.featureFlags.clarification_time_penalty ?? 3} seconds.`
    : `Choose Game Mode for a ${state.roundSeconds}-second round or Rush Hour for a five-customer shift. Progressive hints cost points; clarification costs ${state.featureFlags.clarification_time_penalty ?? 3} seconds. Highest score wins.`;
  matchLabelEl.textContent = "Round not started";
  updateDrinkPreview();
  updateStats();
  setOverlayMode("setup");
}

async function serveDrink() {
  if (!state.roundActive || state.orderResolving) {
    return;
  }
  state.orderResolving = true;
  const responseTimeSeconds = state.currentOrderStartedAt == null
    ? 0
    : Math.max(0, (performance.now() - state.currentOrderStartedAt) / 1000);
  if (state.mode === "rush_hour") {
    clearInterval(state.timerId);
    state.timerId = null;
  }

  const payload = {
    ground_truth_recipe: state.groundTruthRecipe,
    predicted_recipe: state.inferredRecipe,
    submitted_recipe: state.currentRecipe,
  };

  let pointsAwarded;
  let result;
  try {
    const response = await fetch(`${apiBaseUrl}/api/order/evaluate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error("evaluation-failed");
    }

    result = await response.json();
    pointsAwarded = result.points_awarded;
  } catch (error) {
    const localMatches = Object.keys(state.groundTruthRecipe).filter(
      (key) => state.groundTruthRecipe[key] === state.currentRecipe[key]
    ).length;

    const aiMatches = Object.keys(state.groundTruthRecipe).filter(
      (key) => state.groundTruthRecipe[key] === state.inferredRecipe[key]
    ).length;
    pointsAwarded = localMatches === 5 ? 120 : localMatches >= 3 ? 75 : 30;
    result = {
      player_matches: localMatches,
      feedback: `Your drink matched ${localMatches}/5 customer requirements. The AI matched ${aiMatches}/5.`,
    };
  }

  if (!state.roundActive) {
    state.orderResolving = false;
    return;
  }
  const activePlayer = getActivePlayer();
  const recipeAttributes = Object.keys(state.groundTruthRecipe);
  const mistakeAttributes = recipeAttributes.filter(
    (attribute) => state.groundTruthRecipe[attribute] !== state.currentRecipe[attribute],
  );
  const modelFailureAttributes = recipeAttributes.filter(
    (attribute) => state.groundTruthRecipe[attribute] !== state.inferredRecipe[attribute],
  );
  const accuracy = result.player_matches / recipeAttributes.length;
  const confidences = Object.values(state.currentInterpretation?.confidence || {})
    .filter((value) => typeof value === "number" && Number.isFinite(value));
  state.roundOrdersAttempted += 1;
  if (accuracy >= 1) state.roundOrdersCorrect += 1;
  window.BrewAIAnalytics?.track("drink_submitted", {
    difficulty: state.currentCustomer?.difficulty || state.difficultyState.difficulty,
    correct: accuracy >= 1,
    accuracy,
    model_accuracy: 1 - modelFailureAttributes.length / recipeAttributes.length,
    response_time_seconds: responseTimeSeconds,
    points_awarded: pointsAwarded,
    mistake_attributes: mistakeAttributes,
    model_failure_attributes: modelFailureAttributes,
    hints_used: state.hintsThisOrder,
    clarifications_used: state.clarificationsThisOrder,
    low_confidence: confidences.some((confidence) => confidence < 0.5),
    model_disagreement: false,
  }, state.activePlayerIndex, state.mode);
  if (accuracy >= 1) {
    window.BrewAIAnalytics?.track("order_correct", {
      difficulty: state.currentCustomer?.difficulty || state.difficultyState.difficulty,
      response_time_seconds: responseTimeSeconds,
    }, state.activePlayerIndex, state.mode);
  }
  if (state.mode === "rush_hour") {
    feedbackMessageEl.innerHTML = result.feedback;
    await completeRushHourCustomer(
      result.player_matches === 5 ? "correct" : "incorrect",
      pointsAwarded,
      responseTimeSeconds,
    );
    return;
  }

  await applyDifficultyOutcome(
    accuracy,
    responseTimeSeconds,
    mistakeAttributes,
  );
  state.score += pointsAwarded;
  state.served += 1;
  if (activePlayer) {
    activePlayer.score = state.score;
    activePlayer.served = state.served;
  }
  feedbackMessageEl.innerHTML = result.feedback;
  state.orderResolving = false;
  updateStats();
  if (state.timeLeft <= 0) {
    state.currentCustomer = null;
    await finishTurn();
  } else await loadOrder();
}

async function completeRushHourCustomer(outcome, pointsAwarded = 0, responseTimeSeconds = null) {
  if (!state.roundActive || state.mode !== "rush_hour" || !state.rushHourShift) {
    return;
  }
  clearInterval(state.timerId);
  state.timerId = null;
  const elapsed = responseTimeSeconds == null
    ? state.currentOrderSeconds
    : responseTimeSeconds;
  if (outcome === "lost") {
    state.roundOrdersAttempted += 1;
    window.BrewAIAnalytics?.track("order_failed", {
      difficulty: state.currentCustomer?.difficulty || state.difficultyState.difficulty,
      failure_type: "lost",
      response_time_seconds: elapsed,
      hints_used: state.hintsThisOrder,
      clarifications_used: state.clarificationsThisOrder,
    }, state.activePlayerIndex, state.mode);
  }
  state.rushHourShift = recordRushHourCustomer(
    state.rushHourShift,
    outcome,
    elapsed,
    pointsAwarded,
  );
  const mismatchedAttributes = Object.keys(state.groundTruthRecipe).filter(
    (attribute) => state.groundTruthRecipe[attribute] !== state.currentRecipe[attribute],
  );
  await applyDifficultyOutcome(
    outcome === "lost" ? 0 : (Object.keys(state.groundTruthRecipe).length - mismatchedAttributes.length) /
      Object.keys(state.groundTruthRecipe).length,
    elapsed,
    outcome === "lost" ? Object.keys(state.groundTruthRecipe) : mismatchedAttributes,
    outcome === "lost",
  );
  state.score = state.rushHourShift.totalScore;
  state.served = state.rushHourShift.customersServed;
  state.currentOrderStartedAt = null;
  state.orderResolving = false;
  const player = getActivePlayer();
  if (player) {
    player.score = state.score;
    player.served = state.served;
  }
  if (outcome === "lost") {
    feedbackMessageEl.textContent = `${state.currentCustomer?.name || "Customer"} left before the drink was served.`;
  }
  updateStats();
  if (isRushHourComplete(state.rushHourShift)) {
    await finishTurn();
  } else {
    loadOrder();
  }
}

async function skipOrder() {
  if (!state.roundActive || state.orderResolving) {
    return;
  }

  if (state.mode === "rush_hour") {
    const elapsed = state.currentOrderStartedAt == null
      ? 0
      : Math.max(0, (performance.now() - state.currentOrderStartedAt) / 1000);
    await completeRushHourCustomer("lost", 0, elapsed);
    return;
  }

  feedbackMessageEl.textContent =
    "Order skipped. That saves time, but it also means one less chance to score.";
  const elapsed = state.currentOrderStartedAt == null
    ? 0
    : Math.max(0, (performance.now() - state.currentOrderStartedAt) / 1000);
  state.roundOrdersAttempted += 1;
  window.BrewAIAnalytics?.track("order_failed", {
    difficulty: state.currentCustomer?.difficulty || state.difficultyState.difficulty,
    failure_type: "skipped",
    response_time_seconds: elapsed,
    hints_used: state.hintsThisOrder,
    clarifications_used: state.clarificationsThisOrder,
  }, state.activePlayerIndex, state.mode);
  await applyDifficultyOutcome(0, elapsed, Object.keys(state.groundTruthRecipe), true);
  updateStats();
  await loadOrder();
}

function useHint(level) {
  if (!state.roundActive || state.orderResolving) return;
  const hint = advanceHint(
    state.hintState,
    level,
    state.groundTruthRecipe,
    state.currentCustomer?.persona?.id,
    state.currentInterpretation?.confidence,
    state.featureFlags.hint_penalty,
  );
  if (!hint) return;

  state.hintState = hint.state;
  state.hintsThisOrder += 1;
  recordGameEvent("hint_requested", { level: hint.level, attribute: hint.attribute, cost: hint.cost });
  recordGameEvent("hint_level", { level: hint.level });
  recordGameEvent("hint_attribute", { attribute: hint.attribute });
  recordGameEvent("hint_cost", { points: hint.cost });
  if (state.mode === "rush_hour") {
    state.rushHourShift = recordRushHourHint(state.rushHourShift, hint.cost);
    state.score = state.rushHourShift.totalScore;
  } else {
    state.score = Math.max(0, state.score - hint.cost);
  }
  const activePlayer = getActivePlayer();
  if (activePlayer) activePlayer.score = state.score;
  hintResultEl.textContent = `Hint ${hint.level} - ${hint.cost} point${hint.cost === 1 ? "" : "s"}: ${hint.message}`;
  hintResultEl.classList.remove("hidden");
  feedbackMessageEl.textContent = `Hint provided for ${hint.attribute}. ${hint.cost} point${hint.cost === 1 ? "" : "s"} deducted.`;
  updateHintControls();
  updateStats();
}

singlePlayerBtn.addEventListener("click", () => {
  setPlayerMode(1);
});

twoPlayerBtn.addEventListener("click", () => {
  setPlayerMode(2);
});

gameModeBtn.addEventListener("click", () => {
  setGameMode("game");
});

rushHourModeBtn.addEventListener("click", () => {
  setGameMode("rush_hour");
});

startGameBtn.addEventListener("click", async () => {
  startGameBtn.disabled = true;
  try {
    await window.BrewAIAnalytics?.ready;
    startMatchSetup();
  } finally {
    startGameBtn.disabled = false;
  }
});

adaptiveDifficultyToggle.addEventListener("change", () => {
  adaptiveDifficultyLabel.textContent = `Adaptive Difficulty: ${adaptiveDifficultyToggle.checked ? "ON" : "OFF"}`;
  adaptivePolicySelect.disabled = !adaptiveDifficultyToggle.checked || Boolean(state.featureFlags.adaptive_policy);
});

adaptivePolicySelect.addEventListener("change", () => {
  state.adaptivePolicy = adaptivePolicySelect.value;
});

beginTurnBtn.addEventListener("click", () => {
  startTurn();
});

playAgainBtn.addEventListener("click", () => {
  resetToSetup();
});

hintButtons.forEach((button, index) => {
  button.addEventListener("click", () => useHint(index + 1));
});

clarifyBtn.addEventListener("click", askForClarification);

serveBtn.addEventListener("click", () => {
  serveDrink();
});

nextOrderBtn.addEventListener("click", () => {
  skipOrder();
});

buildSelectors();
checkBackend();
lockGameplay(true);
setPlayerMode(1);
setGameMode("game");
updateDrinkPreview();
resetToSetup();
