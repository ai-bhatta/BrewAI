const { test, expect } = require("@playwright/test");
const path = require("node:path");

const recipe = {
  base: "espresso", milk: "oat milk", sweetness: "light sugar", topping: "boba", vibe: "cozy",
};
const confidence = { base: 0.31, milk: 0.35, sweetness: 0.38, topping: 0.28, vibe: 0.4 };
const summary = {
  engagement: { total_sessions: 0, average_session_duration_seconds: 0, average_rounds_per_session: 0, rush_hour_completion_rate: 0 },
  gameplay: { average_score: 0, order_accuracy: 0, average_response_time_seconds: 0, customers_lost: 0, hint_usage_rate: 0, clarification_usage_rate: 0 },
  difficulty: {},
  ai_quality: {
    player_error_by_attribute: { base: 0, milk: 0, sweetness: 0, topping: 0, vibe: 0 },
    model_failure_by_attribute: { base: 0, milk: 0, sweetness: 0, topping: 0, vibe: 0 },
    model_prediction_accuracy: 0, evaluated_orders: 0, low_confidence_prediction_rate: 0, model_disagreement_frequency: 0,
  },
  feedback: { submitted: 0, approval_rate: 0, rejected: 0, candidate_retraining_count: 0 },
  funnel: [], events_recorded: 0,
};

async function captureIfRequested(page, filename, selector = null) {
  if (process.env.BREWAI_CAPTURE_SCREENSHOTS !== "1") return;
  await page.setViewportSize({ width: 1440, height: 1000 });
  const options = { path: path.resolve(__dirname, "../../docs/screenshots", filename), type: "jpeg", quality: 82 };
  if (selector) await page.locator(selector).screenshot(options);
  else await page.screenshot(options);
}

async function gotoApp(page) {
  await page.goto("index.html", { waitUntil: "domcontentloaded" });
}

async function installApiMocks(page) {
  let feedbackEntries = [];
  await page.route("http://127.0.0.1:8000/api/**", async (route) => {
    const request = route.request();
    const { pathname } = new URL(request.url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (pathname === "/api/health") return json({ status: "ok", model_loaded: true });
    if (pathname === "/api/analytics/config") return json({
      session_id: "session_e2e_000001", assignments: {},
      feature_flags: { timer_seconds: 30, hint_penalty: { "1": 1, "2": 2, "3": 3 }, clarification_time_penalty: 3, adaptive_difficulty: false, adaptive_policy: null },
      experiments: {}, minimum_exploratory_sessions_per_variant: 10,
    });
    if (pathname === "/api/analytics/event") return json({ accepted: true }, 202);
    if (pathname === "/api/customer-generation/config") return json({ enabled: true, mode: "templates", model: "not-used", timeout_seconds: 1, maximum_request_characters: 220 });
    if (pathname === "/api/order/interpret") {
      const input = request.postDataJSON();
      return json({ recipe, confidence, source: "e2e-fixture", explanation: [], persona: input.persona, display_name: input.display_name, character_label: input.character_label });
    }
    if (pathname === "/api/order/evaluate") return json({ ai_matches: 3, player_matches: 5, total_attributes: 5, points_awarded: 120, combo_delta: 1, feedback: "Order served successfully." });
    if (pathname === "/api/lab/summary") return json({
      benchmark_available: true, benchmark_winner: "linear_svm", benchmark_macro_f1: 0.977,
      benchmark_average_latency_ms: 3.3, currently_served_model: "Calibrated Logistic Regression",
      currently_served_source: "trained-baseline", production_macro_f1: 0.929,
      production_reason: "Probability-producing production baseline.",
    });
    if (pathname === "/api/lab/examples") return json({ categories: [], records: [] });
    if (pathname === "/api/lab/compare") {
      const models = {};
      for (const name of ["keyword_rules", "multinomial_nb", "logistic_regression", "linear_svm"]) {
        models[name] = { prediction: recipe, confidence, latency_ms: 1.2, available: true, error: null };
      }
      return json({ models, ground_truth: null });
    }
    if (pathname === "/api/feedback" && request.method() === "GET") return json({ entries: feedbackEntries });
    if (pathname === "/api/feedback" && request.method() === "POST") {
      const payload = request.postDataJSON();
      const entry = {
        id: "feedback_e2e_0001", ...payload, source: "ai_lab", status: "pending",
        created_at: new Date().toISOString(), reviewed_at: null, low_confidence: false, priority: 2,
      };
      feedbackEntries = [entry];
      return json({ feedback: entry, similar_entries: [] }, 201);
    }
    if (pathname === "/api/analytics/summary") return json(summary);
    if (pathname === "/api/analytics/experiments") return json({ experiments: {}, minimum_sessions_per_variant: 10 });
    if (pathname === "/api/bandit/metrics") return json({
      decisions: 0, completed_observations: 0, exploration_rate: 0, average_reward: 0,
      actions: Object.fromEntries(["easy", "normal", "ambiguous", "slang", "negation", "multi_clue"].map((key) => [key, { decisions: 0, average_reward: 0, completion_rate: 0 }])),
    });
    if (pathname === "/api/analytics/reset") return json({ reset: true });
    if (pathname === "/api/bandit/reset") return json({ reset: true });
    return json({ detail: `Unmocked E2E endpoint: ${pathname}` }, 404);
  });
}

async function startRound(page, mode = "game") {
  await page.clock.pauseAt(new Date("2026-01-01T00:00:00Z"));
  await installApiMocks(page);
  await gotoApp(page);
  if (mode === "rush_hour") await page.locator("#rush-hour-mode-btn").click();
  await page.locator("#player-one-name").fill("Demo Barista");
  await page.locator("#adaptive-difficulty-toggle").uncheck();
  await page.locator("#start-game-btn").click();
  await expect(page.locator("#begin-turn-btn")).toBeVisible();
  await page.locator("#begin-turn-btn").click();
  await expect(page.locator("#customer-request")).not.toBeEmpty();
  await expect(page.locator("#hint-level-1-btn")).toBeEnabled();
}

test("Game Mode loads a customer, serves a drink, and updates score", async ({ page }) => {
  test.setTimeout(75_000);
  await page.clock.pauseAt(new Date("2026-01-01T00:00:00Z"));
  await installApiMocks(page);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await gotoApp(page);
  await captureIfRequested(page, "home.jpg");
  await page.locator("#player-one-name").fill("Demo Barista");
  await page.locator("#adaptive-difficulty-toggle").uncheck();
  await page.locator("#start-game-btn").click();
  await expect(page.locator("#begin-turn-btn")).toBeVisible();
  await page.locator("#begin-turn-btn").click();
  await expect(page.locator("#customer-request")).not.toBeEmpty();
  await captureIfRequested(page, "game-mode.jpg", "#game-grid");
  await captureIfRequested(page, "customer-persona.jpg", ".panel-order");
  await expect(page.locator("#persona-badge")).toBeVisible();
  await page.locator("#serve-btn").click();
  await expect(page.locator("#score")).toHaveText("120");
  await expect(page.locator("#served-count")).toHaveText("1");
});

test("clarification is available for uncertain output and costs time", async ({ page }) => {
  await startRound(page);
  await expect(page.locator("#clarify-btn")).toBeVisible();
  const before = Number((await page.locator("#round-timer").innerText()).replace("s", ""));
  await page.locator("#clarify-btn").click();
  const after = Number((await page.locator("#round-timer").innerText()).replace("s", ""));
  expect(before - after).toBeGreaterThanOrEqual(3);
  expect(before - after).toBeLessThanOrEqual(5);
  await expect(page.locator("#clarification-reply")).toBeVisible();
  await captureIfRequested(page, "clarification.jpg", ".panel-order");
});

test("progressive hints unlock Nudge, Strong, then Reveal", async ({ page }) => {
  await startRound(page);
  for (const [level, label] of [[1, "Hint 1"], [2, "Hint 2"], [3, "Hint 3"]]) {
    const button = page.locator(`#hint-level-${level}-btn`);
    await expect(button).toBeEnabled();
    await button.click();
    await expect(page.locator("#hint-result")).toContainText(label);
  }
  await captureIfRequested(page, "progressive-hints.jpg", ".panel-order");
  await expect(page.locator("#hint-level-3-btn")).toBeDisabled();
});

test("Rush Hour advances customers and shows the shift summary", async ({ page }) => {
  test.setTimeout(75_000);
  await startRound(page, "rush_hour");
  await captureIfRequested(page, "rush-hour.jpg", "#game-grid");
  for (let customerIndex = 0; customerIndex < 5; customerIndex += 1) {
    await page.locator("#next-order-btn").click();
    if (customerIndex < 4) {
      await expect(page.locator("#shift-progress")).toHaveText(`${customerIndex + 1} / 5`);
      await expect(page.locator("#hint-level-1-btn")).toBeEnabled();
    }
  }
  await expect(page.locator("#results-panel")).toBeVisible();
  await expect(page.locator("#overlay-title")).toHaveText("SHIFT COMPLETE");
  await expect(page.locator("#results-summary")).toContainText("Customers lost: 5");
  await captureIfRequested(page, "rush-hour-summary.jpg", ".overlay-card");
});

test("AI Lab compares models and submits a correction to the pending queue", async ({ page }) => {
  await installApiMocks(page);
  await gotoApp(page);
  await page.locator("#ai-lab-mode-btn").click();
  await page.locator("#lab-request-input").fill("Espresso, oat milk, light sugar, boba, cozy.");
  await page.locator("#lab-analyze-btn").click();
  await expect(page.locator("#lab-results-body tr")).toHaveCount(4);
  await captureIfRequested(page, "ai-lab.jpg", ".lab-results-panel");
  await expect(page.locator("#lab-correction-panel")).toBeVisible();
  await page.locator('[data-corrected="milk"]').selectOption("almond milk");
  await page.locator("#lab-submit-correction-btn").click();
  await expect(page.locator("#lab-feedback-status")).toContainText("pending review");
  await expect(page.locator("#lab-feedback-queue")).toContainText(/Almond Milk/i);
  await captureIfRequested(page, "feedback-review.jpg", ".lab-feedback-panel");
});

test("Analytics dashboard renders an empty-state-safe local summary", async ({ page }) => {
  await installApiMocks(page);
  await gotoApp(page);
  await page.locator("#analytics-mode-btn").click();
  await expect(page.locator("#analytics-dashboard")).toBeVisible();
  await expect(page.locator("#analytics-status")).toContainText("0 local events recorded");
  await expect(page.locator("#analytics-product-metrics")).toContainText("Total sessions");
  await captureIfRequested(page, "analytics.jpg", "#analytics-dashboard");
});
