(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.BrewAILabUtils = api;
  }
})(globalThis, function () {
  const MODEL_ORDER = ["keyword_rules", "multinomial_nb", "logistic_regression", "linear_svm"];
  const MODEL_LABELS = {
    keyword_rules: "Keyword Rules",
    multinomial_nb: "Multinomial Naive Bayes",
    logistic_regression: "Logistic Regression",
    linear_svm: "Linear SVM",
  };
  const ATTRIBUTES = ["base", "milk", "sweetness", "topping", "vibe"];

  function createAnalysisPayload(text, groundTruth = null) {
    const payload = { text: String(text || "").trim() };
    if (groundTruth && Object.keys(groundTruth).length) payload.ground_truth = { ...groundTruth };
    return payload;
  }

  function averageConfidence(modelResult) {
    const values = Object.values(modelResult?.confidence || {}).filter(
      (value) => typeof value === "number" && Number.isFinite(value),
    );
    return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
  }

  function findDisagreements(models) {
    return ATTRIBUTES.flatMap((attribute) => {
      const predictions = MODEL_ORDER.flatMap((modelName) => {
        const result = models?.[modelName];
        const value = result?.available ? result.prediction?.[attribute] : null;
        return typeof value === "string" ? [{ model: modelName, value }] : [];
      });
      return new Set(predictions.map(({ value }) => value)).size > 1
        ? [{ attribute, predictions }]
        : [];
    });
  }

  function compareWithGroundTruth(models, groundTruth) {
    if (!groundTruth) return null;
    return Object.fromEntries(MODEL_ORDER.map((modelName) => {
      const prediction = models?.[modelName]?.prediction || {};
      return [modelName, Object.fromEntries(ATTRIBUTES
        .filter((attribute) => Object.hasOwn(groundTruth, attribute))
        .map((attribute) => [attribute, prediction[attribute] === groundTruth[attribute]]))];
    }));
  }

  function normalizeComparisonResponse(body) {
    if (!body || typeof body !== "object" || !body.models || typeof body.models !== "object") {
      throw new Error("The AI Lab response did not contain model results.");
    }
    const models = Object.fromEntries(MODEL_ORDER.map((modelName) => {
      const result = body.models[modelName];
      return [modelName, result && typeof result === "object"
        ? result
        : { available: false, prediction: null, confidence: null, latency_ms: null, error: "No result returned." }];
    }));
    return { models, ground_truth: body.ground_truth || null };
  }

  function getExampleInput(record) {
    if (!record || typeof record.utterance !== "string") return null;
    const groundTruth = Object.fromEntries(ATTRIBUTES
      .filter((attribute) => typeof record[attribute] === "string")
      .map((attribute) => [attribute, record[attribute]]));
    return { text: record.utterance, groundTruth: Object.keys(groundTruth).length ? groundTruth : null };
  }

  return {
    MODEL_ORDER,
    MODEL_LABELS,
    ATTRIBUTES,
    createAnalysisPayload,
    averageConfidence,
    findDisagreements,
    compareWithGroundTruth,
    normalizeComparisonResponse,
    getExampleInput,
  };
});
