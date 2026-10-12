(function () {
  const API_BASE_URL = "http://127.0.0.1:8000";
  const SESSION_KEY = "brewai_analytics_session";
  const DEFAULT_FLAGS = {
    timer_seconds: 30,
    hint_penalty: { "1": 1, "2": 2, "3": 3 },
    clarification_time_penalty: 3,
    adaptive_difficulty: null,
    adaptive_policy: null,
  };
  const dashboard = document.getElementById("analytics-dashboard");
  const gameGrid = document.getElementById("game-grid");
  const aiLab = document.getElementById("ai-lab");
  const overlay = document.getElementById("game-overlay");
  const modeButton = document.getElementById("analytics-mode-btn");
  const status = document.getElementById("analytics-status");
  let sessionId = sessionStorage.getItem(SESSION_KEY);
  let sessionStartedAt = Date.now();
  let config = { feature_flags: { ...DEFAULT_FLAGS }, assignments: {} };
  let failureCount = 0;

  function newId() {
    return crypto.randomUUID?.() || `local_${Date.now()}_${Math.random().toString(36).slice(2, 12)}`;
  }

  function ensureSession() {
    if (!sessionId) {
      sessionId = newId();
      sessionStorage.setItem(SESSION_KEY, sessionId);
    }
    return sessionId;
  }

  function track(eventName, properties = {}, playerIndex = null, gameMode = "none", keepalive = false) {
    const body = {
      event_name: eventName,
      session_id: ensureSession(),
      player_id: Number.isInteger(playerIndex) ? `${sessionId}_p${playerIndex + 1}` : null,
      game_mode: ["game", "rush_hour", "ai_lab", "analytics"].includes(gameMode) ? gameMode : "none",
      timestamp: new Date().toISOString(),
      properties,
    };
    fetch(`${API_BASE_URL}/api/analytics/event`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      keepalive,
    }).then((response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
    }).catch(() => {
      failureCount += 1;
    });
  }

  async function loadConfiguration() {
    try {
      const response = await fetch(`${API_BASE_URL}/api/analytics/config?session_id=${encodeURIComponent(ensureSession())}`, {
        signal: AbortSignal.timeout(1500),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      config = await response.json();
    } catch (_error) {
      config = { feature_flags: { ...DEFAULT_FLAGS }, assignments: {} };
    }
    return config;
  }

  function metricCard(label, value) {
    const card = document.createElement("div");
    card.className = "analytics-metric";
    const caption = document.createElement("span");
    caption.textContent = label;
    const metric = document.createElement("strong");
    metric.textContent = value;
    card.append(caption, metric);
    return card;
  }

  function formatPercent(value) {
    return `${(Number(value || 0) * 100).toFixed(1)}%`;
  }

  function renderMetrics(container, values) {
    container.replaceChildren();
    values.forEach(([label, value]) => container.appendChild(metricCard(label, value)));
  }

  async function refreshDashboard() {
    status.textContent = "Loading local analytics...";
    try {
      const [summaryResponse, experimentResponse, banditResponse] = await Promise.all([
        fetch(`${API_BASE_URL}/api/analytics/summary`),
        fetch(`${API_BASE_URL}/api/analytics/experiments`),
        fetch(`${API_BASE_URL}/api/bandit/metrics`),
      ]);
      if (!summaryResponse.ok || !experimentResponse.ok || !banditResponse.ok) throw new Error("Analytics API unavailable");
      const summary = await summaryResponse.json();
      const experiments = await experimentResponse.json();
      const bandit = await banditResponse.json();
      renderMetrics(document.getElementById("analytics-product-metrics"), [
        ["Total sessions", String(summary.engagement.total_sessions)],
        ["Avg. session", `${summary.engagement.average_session_duration_seconds.toFixed(1)}s`],
        ["Avg. rounds/session", summary.engagement.average_rounds_per_session.toFixed(1)],
        ["Rush Hour completion", formatPercent(summary.engagement.rush_hour_completion_rate)],
        ["Avg. score", summary.gameplay.average_score.toFixed(1)],
        ["Order accuracy", formatPercent(summary.gameplay.order_accuracy)],
        ["Avg. response", `${summary.gameplay.average_response_time_seconds.toFixed(1)}s`],
        ["Customers lost", String(summary.gameplay.customers_lost)],
        ["Hint usage/order", formatPercent(summary.gameplay.hint_usage_rate)],
        ["Clarification/order", formatPercent(summary.gameplay.clarification_usage_rate)],
      ]);

      const funnel = document.getElementById("analytics-funnel");
      funnel.replaceChildren();
      if (!summary.funnel.length) {
        funnel.textContent = "No gameplay events yet. Complete a round to populate the funnel.";
      }
      summary.funnel.forEach((stage) => {
        const row = document.createElement("div");
        row.className = "analytics-funnel-row";
        const label = document.createElement("span");
        label.textContent = stage.stage.replaceAll("_", " ");
        const value = document.createElement("strong");
        value.textContent = `${stage.count}${stage.conversion_rate == null ? "" : ` | ${formatPercent(stage.conversion_rate)} of previous`}`;
        row.append(label, value);
        funnel.appendChild(row);
      });

      const errors = document.getElementById("analytics-errors");
      errors.replaceChildren();
      const table = document.createElement("table");
      table.className = "lab-table analytics-table";
      const head = document.createElement("thead");
      head.innerHTML = "<tr><th>Attribute</th><th>Player errors</th><th>Model errors</th></tr>";
      table.appendChild(head);
      const body = document.createElement("tbody");
      ["base", "milk", "sweetness", "topping", "vibe"].forEach((attribute) => {
        const row = document.createElement("tr");
        [attribute, summary.ai_quality.player_error_by_attribute[attribute], summary.ai_quality.model_failure_by_attribute[attribute]].forEach((value) => {
          const cell = document.createElement("td");
          cell.textContent = String(value);
          row.appendChild(cell);
        });
        body.appendChild(row);
      });
      table.appendChild(body);
      errors.appendChild(table);

      const difficultyBody = document.getElementById("analytics-difficulty");
      difficultyBody.replaceChildren();
      const difficultyEntries = Object.entries(summary.difficulty);
      if (!difficultyEntries.length) {
        const emptyRow = document.createElement("tr");
        const emptyCell = document.createElement("td");
        emptyCell.colSpan = 6;
        emptyCell.textContent = "No completed orders yet.";
        emptyRow.appendChild(emptyCell);
        difficultyBody.appendChild(emptyRow);
      }
      difficultyEntries.forEach(([difficulty, metrics]) => {
        const row = document.createElement("tr");
        [difficulty, metrics.orders, formatPercent(metrics.success_rate), `${metrics.average_response_time_seconds.toFixed(1)}s`, formatPercent(metrics.hint_usage_rate), formatPercent(metrics.clarification_usage_rate)].forEach((value) => {
          const cell = document.createElement("td");
          cell.textContent = String(value);
          row.appendChild(cell);
        });
        difficultyBody.appendChild(row);
      });

      renderMetrics(document.getElementById("analytics-ai-metrics"), [
        ["Model accuracy (labeled orders)", formatPercent(summary.ai_quality.model_prediction_accuracy)],
        ["Evaluated orders", String(summary.ai_quality.evaluated_orders)],
        ["Low-confidence rate", formatPercent(summary.ai_quality.low_confidence_prediction_rate)],
        ["AI Lab disagreement cases", String(summary.ai_quality.model_disagreement_frequency)],
      ]);
      renderMetrics(document.getElementById("analytics-feedback-metrics"), [
        ["Feedback submitted", String(summary.feedback.submitted)],
        ["Approval rate", formatPercent(summary.feedback.approval_rate)],
        ["Rejected feedback", String(summary.feedback.rejected)],
        ["Candidate reports", String(summary.feedback.candidate_retraining_count)],
      ]);
      renderMetrics(document.getElementById("analytics-bandit-metrics"), [
        ["Decisions", String(bandit.decisions)],
        ["Completed outcomes", String(bandit.completed_observations)],
        ["Exploration rate", formatPercent(bandit.exploration_rate)],
        ["Average reward", bandit.average_reward.toFixed(3)],
      ]);
      const actionMetrics = document.getElementById("analytics-bandit-actions");
      actionMetrics.replaceChildren();
      Object.entries(bandit.actions).forEach(([action, metrics]) => {
        const row = document.createElement("div");
        row.className = "analytics-funnel-row";
        const label = document.createElement("span");
        label.textContent = action.replaceAll("_", " ");
        const value = document.createElement("strong");
        value.textContent = `${metrics.decisions} decisions | reward ${metrics.average_reward.toFixed(3)} | completion ${formatPercent(metrics.completion_rate)}`;
        row.append(label, value);
        actionMetrics.appendChild(row);
      });
      renderExperiments(experiments);
      status.textContent = `${summary.events_recorded} local events recorded.${failureCount ? ` ${failureCount} event write(s) could not reach the local API.` : ""}`;
    } catch (error) {
      status.textContent = `Could not load analytics: ${error.message}`;
    }
  }

  function renderExperiments(result) {
    const container = document.getElementById("analytics-experiments");
    container.replaceChildren();
    const experimentEntries = Object.entries(result.experiments);
    if (!experimentEntries.length) {
      container.textContent = "No experiment definitions are available.";
    }
    experimentEntries.forEach(([name, experiment]) => {
      const card = document.createElement("article");
      card.className = "analytics-experiment";
      const title = document.createElement("h4");
      title.textContent = name.replaceAll("_", " ");
      const hypothesis = document.createElement("p");
      hypothesis.textContent = `Hypothesis: ${experiment.hypothesis}`;
      const metric = document.createElement("p");
      const delta = experiment.primary_metric_delta;
      metric.textContent = `Primary metric (${experiment.primary_metric}): ${delta >= 0 ? "+" : ""}${delta}`;
      const guardrail = document.createElement("p");
      guardrail.textContent = `Guardrails: ${(experiment.guardrail_metrics || [experiment.guardrail_metric]).join(", ")}`;
      const assignedVariant = config.assignments?.[name];
      const assignment = document.createElement("p");
      assignment.textContent = assignedVariant
        ? `This browser session: Variant ${assignedVariant} (${experiment.variants[assignedVariant]?.label || "assigned"}).`
        : "This browser session has no assignment.";
      const variants = document.createElement("div");
      variants.className = "analytics-variant-grid";
      Object.entries(experiment.variants).forEach(([variant, data]) => {
        const item = document.createElement("div");
        item.className = "analytics-variant";
        item.textContent = `${variant} | ${data.label} | ${data.sessions} sessions | success without hints ${formatPercent(data.successful_orders_without_hints_rate)} | completion ${formatPercent(data.completion_rate)} | lost ${formatPercent(data.customer_loss_rate)} | hints ${formatPercent(data.hint_usage_rate)} | clarification ${formatPercent(data.clarification_usage_rate)} | response ${data.average_response_time_seconds.toFixed(1)}s`;
        variants.appendChild(item);
      });
      const note = document.createElement("p");
      note.textContent = experiment.sample_warning || "Exploratory descriptive result; more observation is recommended.";
      card.append(title, hypothesis, metric, guardrail, assignment, variants, note);
      container.appendChild(card);
    });
  }

  function openDashboard() {
    dashboard.classList.remove("hidden");
    gameGrid.classList.add("hidden");
    aiLab.classList.add("hidden");
    overlay.classList.add("hidden");
    modeButton.classList.add("active");
    document.getElementById("game-mode-btn").classList.remove("active");
    document.getElementById("rush-hour-mode-btn").classList.remove("active");
    document.getElementById("ai-lab-mode-btn").classList.remove("active");
    track("analytics_view_opened", {}, null, "analytics");
    refreshDashboard();
  }

  function closeDashboard() {
    dashboard.classList.add("hidden");
    gameGrid.classList.remove("hidden");
    overlay.classList.remove("hidden");
    modeButton.classList.remove("active");
    const modeId = window.BrewAIGameMode === "rush_hour" ? "rush-hour-mode-btn" : "game-mode-btn";
    document.getElementById(modeId).classList.add("active");
  }

  async function exportCsv() {
    try {
      const response = await fetch(`${API_BASE_URL}/api/analytics/export?format=csv`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "brewai-analytics.csv";
      link.click();
      URL.revokeObjectURL(url);
      status.textContent = "CSV exported locally.";
    } catch (error) {
      status.textContent = `Export failed: ${error.message}`;
    }
  }

  async function resetAnalytics() {
    if (!window.confirm("Reset local analytics events and experiment assignments only? Feedback, models, and datasets will not be touched.")) return;
    try {
      const response = await fetch(`${API_BASE_URL}/api/analytics/reset`, { method: "POST" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      window.BrewAIAnalytics.rotateSession();
      await loadConfiguration();
      await refreshDashboard();
    } catch (error) {
      status.textContent = `Analytics reset failed: ${error.message}`;
    }
  }

  async function resetBandit() {
    if (!window.confirm("Reset only contextual-bandit decisions and learned weights? Analytics, feedback, datasets, and models will remain.")) return;
    try {
      const response = await fetch(`${API_BASE_URL}/api/bandit/reset`, { method: "POST" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      window.BrewAIAnalytics.rotateSession();
      await loadConfiguration();
      status.textContent = "Bandit learning state reset. Product analytics were preserved.";
      await refreshDashboard();
    } catch (error) {
      status.textContent = `Bandit reset failed: ${error.message}`;
    }
  }

  ensureSession();
  const ready = loadConfiguration();
  track("session_started", { source: "local_browser" }, null, "none");
  window.addEventListener("beforeunload", () => {
    track("session_ended", { duration_seconds: Math.max(0, (Date.now() - sessionStartedAt) / 1000) }, null, "none", true);
  });
  modeButton.addEventListener("click", openDashboard);
  document.getElementById("analytics-back-btn").addEventListener("click", closeDashboard);
  document.getElementById("analytics-refresh-btn")?.addEventListener("click", refreshDashboard);
  document.getElementById("analytics-export-btn").addEventListener("click", exportCsv);
  document.getElementById("analytics-reset-btn").addEventListener("click", resetAnalytics);
  document.getElementById("analytics-bandit-reset-btn")?.addEventListener("click", resetBandit);

  window.BrewAIAnalytics = {
    ready,
    track,
    getSessionId: ensureSession,
    getFeatureFlags: () => config.feature_flags || { ...DEFAULT_FLAGS },
    getAssignments: () => config.assignments || {},
    refreshDashboard,
    rotateSession: () => {
      sessionId = newId();
      sessionStorage.setItem(SESSION_KEY, sessionId);
      sessionStartedAt = Date.now();
      track("session_started", { source: "local_browser" }, null, "none");
    },
  };
})();
