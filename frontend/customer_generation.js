(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.BrewAICustomerGeneration = api.createCustomerGenerationClient({
    track: (...args) => root.BrewAIAnalytics?.track(...args),
  });
})(globalThis, function () {
  const DEFAULT_CONFIG = { enabled: true, mode: "auto", model: "qwen3:4b", timeout_seconds: 4, maximum_request_characters: 220 };

  function createCustomerGenerationClient(options = {}) {
    const baseUrl = options.baseUrl || "http://127.0.0.1:8000";
    const fetchImpl = options.fetchImpl || globalThis.fetch;
    const track = options.track || (() => {});
    let config = { ...DEFAULT_CONFIG };

    async function loadConfig() {
      try {
        const response = await fetchImpl(`${baseUrl}/api/customer-generation/config`);
        if (!response.ok) throw new Error("config unavailable");
        const result = await response.json();
        config = { ...DEFAULT_CONFIG, ...result };
      } catch (_error) {
        config = { ...DEFAULT_CONFIG };
      }
      return config;
    }

    function recordLatency(source, latencyMs, context) {
      track("generation_latency", { source, latency_ms: Math.max(0, Number(latencyMs) || 0), context }, null, "none");
      track("generation_source", { source, context }, null, "none");
    }

    async function generate(customer, context = "game", forcedMode = null) {
      await ready;
      const mode = forcedMode || config.mode || "auto";
      const started = Date.now();
      track("generation_requested", { mode, context }, null, "none");
      if (mode === "templates") {
        recordLatency("template", 0, context);
        return { request: customer.request, source: "template", latency_ms: 0 };
      }
      const fallback = (reason, latency = Date.now() - started) => {
        track("generation_failed", { reason, latency_ms: Math.max(0, latency), context }, null, "none");
        track("generation_fallback", { reason, source: "template", context }, null, "none");
        recordLatency("template", latency, context);
        return { request: customer.request, source: "template", latency_ms: latency, fallback_reason: reason };
      };
      if (!config.enabled) return fallback("disabled");

      let timeoutId;
      try {
        const request = fetchImpl(`${baseUrl}/api/customer-generation/generate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            canonical_recipe: customer.recipe,
            persona: customer.persona,
            difficulty: customer.difficulty,
            mode: mode === "local_ai" ? "local_ai" : "auto",
          }),
        }).then(async (response) => {
          const body = await response.json();
          if (!response.ok) throw new Error("unavailable");
          return body;
        });
        const timeout = new Promise((_resolve, reject) => {
          timeoutId = setTimeout(() => reject(new Error("timeout")), options.timeoutMs ?? (config.timeout_seconds * 1000 + 1000));
        });
        const result = await Promise.race([request, timeout]);
        const latency = result.latency_ms ?? (Date.now() - started);
        if (!result.success || !result.request) return fallback(result.fallback_reason || "unavailable", latency);
        track("generation_succeeded", { source: "local_ai", cache_hit: Boolean(result.cache_hit), latency_ms: latency, context }, null, "none");
        recordLatency("local_ai", latency, context);
        return { request: result.request, source: "local_ai", latency_ms: latency, cache_hit: Boolean(result.cache_hit) };
      } catch (error) {
        return fallback(error.message === "timeout" ? "timeout" : "unavailable");
      } finally {
        clearTimeout(timeoutId);
      }
    }

    async function compare(payload) {
      await ready;
      track("generation_requested", { mode: "local_ai", context: "ai_lab" }, null, "none");
      try {
        const response = await fetchImpl(`${baseUrl}/api/customer-generation/compare`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...payload, mode: "local_ai" }),
          signal: typeof AbortSignal !== "undefined" && AbortSignal.timeout
            ? AbortSignal.timeout(config.timeout_seconds * 1000 + 1500) : undefined,
        });
        const result = await response.json();
        if (!response.ok) throw new Error("comparison unavailable");
        if (result.local_ai.success) {
          track("generation_succeeded", { source: "local_ai", cache_hit: Boolean(result.local_ai.cache_hit), latency_ms: result.local_ai.latency_ms, context: "ai_lab" }, null, "none");
        } else {
          track("generation_failed", { reason: result.local_ai.fallback_reason || "unavailable", latency_ms: result.local_ai.latency_ms, context: "ai_lab" }, null, "none");
          track("generation_fallback", { reason: result.local_ai.fallback_reason || "unavailable", source: "template", context: "ai_lab" }, null, "none");
        }
        recordLatency(result.local_ai.success ? "local_ai" : "template", result.local_ai.latency_ms, "ai_lab");
        return result;
      } catch (_error) {
        return null;
      }
    }

    const ready = loadConfig();
    return { ready, generate, compare, getConfig: () => ({ ...config }) };
  }

  return { DEFAULT_CONFIG, createCustomerGenerationClient };
});
