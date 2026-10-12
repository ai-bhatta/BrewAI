const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

test("analytics client keeps an anonymous stable session and event failure does not block callers", async () => {
  const source = fs.readFileSync(require.resolve("../frontend/analytics.js"), "utf8");
  const elements = new Map();
  const makeElement = () => ({
    addEventListener() {},
    classList: { add() {}, remove() {} },
    replaceChildren() {},
  });
  const document = {
    getElementById(id) {
      if (!elements.has(id)) elements.set(id, makeElement());
      return elements.get(id);
    },
  };
  const storage = new Map();
  const sessionStorage = {
    getItem: (key) => storage.get(key) || null,
    setItem: (key, value) => storage.set(key, value),
  };
  const window = { addEventListener() {} };
  const context = {
    window,
    document,
    sessionStorage,
    crypto: { randomUUID: () => "session_analytics_0001" },
    fetch: () => Promise.reject(new Error("local API offline")),
    AbortSignal,
    URL,
    Blob,
    Date,
    Math,
    console,
  };
  vm.runInNewContext(source, context);
  await window.BrewAIAnalytics.ready;
  const session = window.BrewAIAnalytics.getSessionId();
  assert.equal(session, window.BrewAIAnalytics.getSessionId());
  assert.doesNotThrow(() => window.BrewAIAnalytics.track("hint_requested", { level: 1, attribute: "milk", cost: 1 }, 0, "game"));
});
