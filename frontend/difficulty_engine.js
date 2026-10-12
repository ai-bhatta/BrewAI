(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.BrewAIDifficulty = api;
  }
})(globalThis, function () {
  const DIFFICULTIES = ["easy", "normal", "ambiguous", "slang", "negation", "multi_clue"];
  const CONFIG = Object.freeze({
    HISTORY_LIMIT: 5,
    MINIMUM_ORDERS: 3,
    LOW_ACCURACY: 0.55,
    HIGH_ACCURACY: 0.85,
    HIGH_HINT_ORDER_RATIO: 0.6,
    HIGH_CLARIFICATION_ORDER_RATIO: 0.6,
    FAST_RESPONSE_SECONDS: 13,
    SLOW_RESPONSE_SECONDS: 22,
    MISTAKE_ATTRIBUTE_COUNT: 2,
  });

  function createPerformanceState(initialDifficulty = "normal") {
    return {
      difficulty: DIFFICULTIES.includes(initialDifficulty) ? initialDifficulty : "normal",
      history: [],
      currentStreak: 0,
    };
  }

  function recordOrder(performanceState, order) {
    const correct = Boolean(order.correct);
    const entry = {
      accuracy: Math.max(0, Math.min(1, Number(order.accuracy) || 0)),
      responseTimeSeconds: Math.max(0, Number(order.responseTimeSeconds) || 0),
      hintsUsed: Math.max(0, Number(order.hintsUsed) || 0),
      clarificationsUsed: Math.max(0, Number(order.clarificationsUsed) || 0),
      correct,
      mistakeAttributes: [...new Set(order.mistakeAttributes || [])],
    };
    return {
      ...performanceState,
      history: [...performanceState.history, entry].slice(-CONFIG.HISTORY_LIMIT),
      currentStreak: correct ? performanceState.currentStreak + 1 : 0,
    };
  }

  function summarizePerformance(performanceState) {
    const history = performanceState.history;
    const count = history.length;
    const average = (select) => count
      ? history.reduce((sum, entry) => sum + select(entry), 0) / count
      : 0;
    const mistakeCounts = {};
    history.forEach((entry) => entry.mistakeAttributes.forEach((attribute) => {
      mistakeCounts[attribute] = (mistakeCounts[attribute] || 0) + 1;
    }));
    return {
      orderCount: count,
      recentAccuracy: average((entry) => entry.accuracy),
      averageResponseTime: average((entry) => entry.responseTimeSeconds),
      hintsUsed: average((entry) => entry.hintsUsed),
      hintOrderRatio: average((entry) => entry.hintsUsed > 0 ? 1 : 0),
      clarificationsUsed: average((entry) => entry.clarificationsUsed),
      clarificationOrderRatio: average((entry) => entry.clarificationsUsed > 0 ? 1 : 0),
      recentMistakeAttributes: Object.keys(mistakeCounts).filter(
        (attribute) => mistakeCounts[attribute] >= CONFIG.MISTAKE_ATTRIBUTE_COUNT,
      ),
      mistakeCounts,
    };
  }

  function evaluateDifficulty(performanceState, options = {}) {
    const adaptiveEnabled = options.adaptiveEnabled !== false;
    const fixedDifficulty = DIFFICULTIES.includes(options.fixedDifficulty)
      ? options.fixedDifficulty
      : "normal";
    const previous = performanceState.difficulty;
    const metrics = summarizePerformance(performanceState);
    let reason = "stable_performance";
    let next = previous;

    if (!adaptiveEnabled) {
      next = fixedDifficulty;
      reason = "adaptive_disabled";
    } else if (metrics.orderCount < CONFIG.MINIMUM_ORDERS) {
      reason = "insufficient_history";
    } else {
      const index = DIFFICULTIES.indexOf(previous);
      if (metrics.recentAccuracy < CONFIG.LOW_ACCURACY) {
        next = DIFFICULTIES[Math.max(0, index - 1)];
        reason = "low_accuracy";
      } else if (metrics.hintOrderRatio >= CONFIG.HIGH_HINT_ORDER_RATIO) {
        next = DIFFICULTIES[Math.max(0, index - 1)];
        reason = "high_hint_usage";
      } else if (metrics.clarificationOrderRatio >= CONFIG.HIGH_CLARIFICATION_ORDER_RATIO) {
        next = DIFFICULTIES[Math.max(0, index - 1)];
        reason = "high_clarification_usage";
      } else if (metrics.averageResponseTime >= CONFIG.SLOW_RESPONSE_SECONDS) {
        next = DIFFICULTIES[Math.max(0, index - 1)];
        reason = "slow_response";
      } else if (
        metrics.recentAccuracy >= CONFIG.HIGH_ACCURACY &&
        metrics.averageResponseTime <= CONFIG.FAST_RESPONSE_SECONDS
      ) {
        next = DIFFICULTIES[Math.min(DIFFICULTIES.length - 1, index + 1)];
        reason = "high_accuracy";
      } else if (performanceState.currentStreak >= 3) {
        next = DIFFICULTIES[Math.min(DIFFICULTIES.length - 1, index + 1)];
        reason = "winning_streak";
      }
    }

    return {
      state: { ...performanceState, difficulty: next },
      decision: {
        previous,
        next,
        changed: previous !== next,
        reason,
        reasonText: {
          adaptive_disabled: "Adaptive difficulty is disabled.",
          insufficient_history: "Waiting for more completed orders.",
          low_accuracy: "Recent order accuracy is low.",
          high_hint_usage: "Recent orders rely heavily on hints.",
          high_clarification_usage: "Recent orders rely heavily on clarification.",
          slow_response: "Recent response times are slow.",
          high_accuracy: "Recent accuracy is high and responses are fast.",
          winning_streak: "The player is on a three-order correct streak.",
          stable_performance: "Recent performance is steady.",
        }[reason],
        metrics,
      },
    };
  }

  return { DIFFICULTIES, CONFIG, createPerformanceState, recordOrder, summarizePerformance, evaluateDifficulty };
});
