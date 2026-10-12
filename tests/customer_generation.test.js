const test = require("node:test");
const assert = require("node:assert/strict");
const { createCustomerGenerationClient } = require("../frontend/customer_generation.js");

const customer = {
  request: "Template order",
  recipe: { base: "espresso", milk: "oat milk", sweetness: "light sugar", topping: "boba", vibe: "cozy" },
  persona: { id: "coffee_snob", display_name: "Coffee Snob" },
  difficulty: "normal",
};

test("templates mode returns immediately without requesting model dialogue", async () => {
  const events = [];
  let calls = 0;
  const client = createCustomerGenerationClient({
    timeoutMs: 20,
    fetchImpl: async (url) => {
      calls += 1;
      if (url.endsWith("/config")) return { ok: true, json: async () => ({ enabled: true, mode: "templates" }) };
      throw new Error("unexpected generation request");
    },
    track: (name) => events.push(name),
  });
  const result = await client.generate(customer);
  assert.equal(result.source, "template");
  assert.equal(result.request, customer.request);
  assert.equal(calls, 1);
  assert.ok(events.includes("generation_source"));
});

test("a slow local API returns the template fallback instead of blocking", async () => {
  const client = createCustomerGenerationClient({
    timeoutMs: 10,
    fetchImpl: async (url) => {
      if (url.endsWith("/config")) return { ok: true, json: async () => ({ enabled: true, mode: "auto", timeout_seconds: 1 }) };
      return new Promise(() => {});
    },
  });
  const result = await client.generate(customer);
  assert.equal(result.source, "template");
  assert.equal(result.request, customer.request);
  assert.equal(result.fallback_reason, "timeout");
});

test("validated local responses and source events are surfaced", async () => {
  const events = [];
  const client = createCustomerGenerationClient({
    fetchImpl: async (url) => url.endsWith("/config")
      ? { ok: true, json: async () => ({ enabled: true, mode: "local_ai", timeout_seconds: 2 }) }
      : { ok: true, json: async () => ({ success: true, request: "Validated locally", source: "local_ai", latency_ms: 12, cache_hit: true }) },
    track: (name, props) => events.push({ name, props }),
  });
  const result = await client.generate(customer);
  assert.equal(result.source, "local_ai");
  assert.equal(result.cache_hit, true);
  assert.ok(events.some((event) => event.name === "generation_succeeded"));
  assert.ok(events.some((event) => event.name === "generation_latency"));
});
