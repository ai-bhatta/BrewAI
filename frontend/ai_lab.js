(function () {
  const API_BASE_URL = "http://127.0.0.1:8000";
  const utils = window.BrewAILabUtils;
  const aiLabEl = document.getElementById("ai-lab");
  const gameGridEl = document.getElementById("game-grid");
  const overlayEl = document.getElementById("game-overlay");
  const modeButton = document.getElementById("ai-lab-mode-btn");
  const requestInput = document.getElementById("lab-request-input");
  const analyzeBtn = document.getElementById("lab-analyze-btn");
  const statusEl = document.getElementById("lab-status");
  const groundTruthToggle = document.getElementById("lab-ground-truth-toggle");
  const groundTruthFields = document.getElementById("lab-ground-truth-fields");
  const exampleCategory = document.getElementById("lab-category-filter");
  const exampleSelect = document.getElementById("lab-record-select");
  const loadExampleBtn = document.getElementById("lab-load-example-btn");
  const difficultySelect = document.getElementById("lab-difficulty-select");
  const generateDifficultyBtn = document.getElementById("lab-generate-difficulty-btn");
  const generationCompareBtn = document.getElementById("lab-compare-generation-btn");
  const generationComparisonEl = document.getElementById("lab-generation-comparison");
  const resultBody = document.getElementById("lab-results-body");
  const disagreementEl = document.getElementById("lab-disagreements");
  const confidenceContentEl = document.getElementById("lab-confidence-content");
  const benchmarkSummaryEl = document.getElementById("lab-benchmark-summary");
  const correctionPanel = document.getElementById("lab-correction-panel");
  const correctionModel = document.getElementById("lab-correction-model");
  const correctionFields = document.getElementById("lab-corrected-recipe");
  const correctionSubmit = document.getElementById("lab-submit-correction-btn");
  const feedbackStatus = document.getElementById("lab-feedback-status");
  const feedbackQueue = document.getElementById("lab-feedback-queue");
  const feedbackRefresh = document.getElementById("lab-refresh-feedback-btn");
  const examplesByCategory = new Map();
  let nextSeed = 200;
  let latestComparison = null;
  window.BrewAIGameMode = window.BrewAIGameMode || "game";

  window.BrewAILabEvents = window.BrewAILabEvents || [];

  function recordEvent(type, details = {}) {
    window.BrewAILabEvents.push({ type, ...details, timestamp: Date.now() });
    window.BrewAIAnalytics?.track(type, details, null, "ai_lab");
  }

  function setExpectedRecipe(recipe) {
    if (!recipe) return;
    groundTruthToggle.checked = true;
    groundTruthFields.classList.remove("hidden");
    groundTruthFields.querySelectorAll("[data-truth]").forEach((select) => {
      if (Object.hasOwn(recipe, select.dataset.truth)) select.value = recipe[select.dataset.truth];
    });
  }

  function getExpectedRecipe() {
    if (!groundTruthToggle.checked) return null;
    return Object.fromEntries([...groundTruthFields.querySelectorAll("[data-truth]")]
      .map((select) => [select.dataset.truth, select.value]));
  }

  function setFreeFormRequest(text) {
    requestInput.value = text;
    latestComparison = null;
    correctionPanel.classList.add("hidden");
    groundTruthToggle.checked = false;
    groundTruthFields.classList.add("hidden");
    statusEl.textContent = "Free-form request loaded. Results will show agreement, not correctness.";
  }

  function populateExampleOptions() {
    const category = exampleCategory.value;
    const records = examplesByCategory.get(category) || [];
    exampleSelect.replaceChildren();
    if (!records.length) {
      exampleSelect.add(new Option("No examples in this category", ""));
      exampleSelect.disabled = true;
      loadExampleBtn.disabled = true;
      return;
    }
    records.forEach((record, index) => {
      exampleSelect.add(new Option(`${index + 1}. ${record.utterance}`, String(index)));
    });
    exampleSelect.disabled = false;
    loadExampleBtn.disabled = false;
  }

  async function loadRobustnessExamples() {
    try {
      const response = await fetch(`${API_BASE_URL}/api/lab/examples`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      examplesByCategory.clear();
      data.records.forEach((record) => {
        const rows = examplesByCategory.get(record.category) || [];
        rows.push(record);
        examplesByCategory.set(record.category, rows);
      });
      exampleCategory.replaceChildren();
      data.categories.forEach((category) => exampleCategory.add(new Option(category, category)));
      exampleCategory.disabled = false;
      populateExampleOptions();
    } catch (error) {
      exampleCategory.replaceChildren(new Option("Examples unavailable", ""));
      exampleCategory.disabled = true;
      exampleSelect.replaceChildren(new Option("Could not load robustness data", ""));
      exampleSelect.disabled = true;
      loadExampleBtn.disabled = true;
      statusEl.textContent = `Robustness examples unavailable: ${error.message}`;
    }
  }

  async function loadBenchmarkSummary() {
    try {
      const response = await fetch(`${API_BASE_URL}/api/lab/summary`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const summary = await response.json();
      benchmarkSummaryEl.replaceChildren();
      if (summary.benchmark_available) {
        const benchmark = document.createElement("p");
        const label = document.createElement("strong");
        label.textContent = "Benchmark winner: ";
        benchmark.append(label, `${utils.MODEL_LABELS[summary.benchmark_winner] || summary.benchmark_winner} | Grouped holdout macro F1: ${Number(summary.benchmark_macro_f1).toFixed(3)} | Average latency: ${Number(summary.benchmark_average_latency_ms).toFixed(3)} ms`);
        benchmarkSummaryEl.appendChild(benchmark);
      } else {
        const unavailable = document.createElement("p");
        unavailable.textContent = summary.error || "Saved benchmark report unavailable.";
        benchmarkSummaryEl.appendChild(unavailable);
      }
      const served = document.createElement("p");
      const servedLabel = document.createElement("strong");
      servedLabel.textContent = "Currently served model: ";
      served.append(servedLabel, `${summary.currently_served_model} (${summary.currently_served_source})`);
      benchmarkSummaryEl.appendChild(served);
      if (Number.isFinite(summary.production_macro_f1)) {
        const production = document.createElement("p");
        production.textContent = `Production grouped-holdout macro F1: ${summary.production_macro_f1.toFixed(3)}. ${summary.production_reason || ""}`;
        benchmarkSummaryEl.appendChild(production);
      }
      if (summary.comparison_model_metadata) {
        const comparisonMetadata = summary.comparison_model_metadata;
        const provenance = document.createElement("p");
        provenance.textContent = `AI Lab models: v${comparisonMetadata.artifact_version || 1}; ${comparisonMetadata.training_examples || "metadata pending"} canonical training examples; dataset SHA-256 ${comparisonMetadata.dataset_sha256 || "pending first analysis"}.`;
        benchmarkSummaryEl.appendChild(provenance);
      }
    } catch (error) {
      benchmarkSummaryEl.textContent = `Saved benchmark summary unavailable: ${error.message}`;
    }
  }

  function renderDisagreements(models) {
    disagreementEl.replaceChildren();
    const disagreements = utils.findDisagreements(models);
    if (!disagreements.length) {
      const message = document.createElement("p");
      message.className = "lab-disagreement";
      message.textContent = "No disagreements among available model predictions.";
      disagreementEl.appendChild(message);
      return;
    }
    disagreements.forEach(({ attribute, predictions }) => {
      const line = document.createElement("p");
      line.className = "lab-disagreement";
      const values = predictions.map(({ model, value }) => `${utils.MODEL_LABELS[model]}: ${value}`).join(" | ");
      line.textContent = `${attribute[0].toUpperCase()}${attribute.slice(1)} disagreement: ${values}`;
      disagreementEl.appendChild(line);
    });
  }

  function renderConfidence(models) {
    confidenceContentEl.replaceChildren();
    const grid = document.createElement("div");
    grid.className = "lab-confidence-grid";
    utils.MODEL_ORDER.forEach((modelName) => {
      const result = models[modelName];
      const card = document.createElement("section");
      card.className = "lab-confidence-card";
      const title = document.createElement("h4");
      title.textContent = utils.MODEL_LABELS[modelName];
      card.appendChild(title);
      if (!result.available || !result.confidence) {
        const unavailable = document.createElement("p");
        unavailable.textContent = result.available ? "Confidence unavailable" : result.error || "Model unavailable";
        card.appendChild(unavailable);
      } else {
        utils.ATTRIBUTES.forEach((attribute) => {
          const confidence = result.confidence[attribute];
          const line = document.createElement("p");
          const prediction = result.prediction?.[attribute] || "—";
          const percent = typeof confidence === "number" ? `${(confidence * 100).toFixed(1)}%` : "—";
          line.textContent = `${attribute}: ${prediction} | ${percent}`;
          card.appendChild(line);
        });
      }
      grid.appendChild(card);
    });
    confidenceContentEl.appendChild(grid);
  }

  function renderResults(comparison, expectedRecipe) {
    const models = comparison.models;
    const correctness = utils.compareWithGroundTruth(models, expectedRecipe);
    resultBody.replaceChildren();
    utils.MODEL_ORDER.forEach((modelName) => {
      const result = models[modelName];
      const row = document.createElement("tr");
      const modelCell = document.createElement("td");
      modelCell.textContent = utils.MODEL_LABELS[modelName];
      row.appendChild(modelCell);
      if (!result.available) {
        const errorCell = document.createElement("td");
        errorCell.colSpan = 7;
        errorCell.className = "model-error";
        errorCell.textContent = result.error || "Model unavailable";
        row.appendChild(errorCell);
      } else {
        utils.ATTRIBUTES.forEach((attribute) => {
          const cell = document.createElement("td");
          const value = result.prediction?.[attribute] || "—";
          if (correctness?.[modelName] && Object.hasOwn(correctness[modelName], attribute)) {
            const matches = correctness[modelName][attribute];
            cell.className = matches ? "prediction-correct" : "prediction-incorrect";
            cell.textContent = `${value} (${matches ? "correct" : "incorrect"})`;
          } else {
            cell.textContent = value;
          }
          row.appendChild(cell);
        });
        const averageCell = document.createElement("td");
        const average = utils.averageConfidence(result);
        averageCell.textContent = average == null ? "—" : `${(average * 100).toFixed(1)}%`;
        row.appendChild(averageCell);
        const latencyCell = document.createElement("td");
        latencyCell.textContent = typeof result.latency_ms === "number"
          ? result.latency_ms.toFixed(3)
          : "—";
        row.appendChild(latencyCell);
      }
      resultBody.appendChild(row);
    });
    renderDisagreements(models);
    renderConfidence(models);
  }

  function selectedModelResult() {
    return latestComparison?.models?.[correctionModel.value];
  }

  function prefillCorrection() {
    const result = selectedModelResult();
    const available = Boolean(result?.available && result.prediction);
    correctionPanel.classList.toggle("hidden", !latestComparison);
    correctionSubmit.disabled = !available;
    correctionFields.querySelectorAll("[data-corrected]").forEach((select) => {
      select.disabled = !available;
      if (available && Object.hasOwn(result.prediction, select.dataset.corrected)) {
        select.value = result.prediction[select.dataset.corrected];
      }
    });
    feedbackStatus.textContent = available
      ? "Review and edit the proposed values, then explicitly submit this correction."
      : "This model did not return a complete prediction for the request.";
  }

  function changedAttributes(predicted, corrected) {
    return utils.ATTRIBUTES.filter((attribute) => predicted?.[attribute] !== corrected?.[attribute]);
  }

  async function submitCorrection() {
    const result = selectedModelResult();
    if (!requestInput.value.trim() || !result?.available || !result.prediction) return;
    const corrected = Object.fromEntries([...correctionFields.querySelectorAll("[data-corrected]")]
      .map((select) => [select.dataset.corrected, select.value]));
    if (!changedAttributes(result.prediction, corrected).length) {
      feedbackStatus.textContent = "No values changed. Submit only a genuine correction.";
      return;
    }
    correctionSubmit.disabled = true;
    feedbackStatus.textContent = "Submitting correction to the pending review queue...";
    const payload = {
      text: requestInput.value.trim(),
      model: correctionModel.value,
      predicted: result.prediction,
      corrected,
      confidence: result.confidence || null,
      model_disagreement: utils.findDisagreements(latestComparison.models).length > 0,
    };
    try {
      const response = await fetch(`${API_BASE_URL}/api/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || `HTTP ${response.status}`);
      recordEvent("feedback_submitted", { id: body.feedback.id, model: payload.model });
      const similarNote = body.similar_entries?.length
        ? ` Similar wording found in ${body.similar_entries.length} existing item(s); please review the queue.`
        : "";
      feedbackStatus.textContent = `Correction submitted as pending review.${similarNote}`;
      await loadFeedbackQueue();
    } catch (error) {
      feedbackStatus.textContent = `Could not submit correction: ${error.message}`;
    } finally {
      correctionSubmit.disabled = false;
    }
  }

  function makeRecipeLine(label, recipe) {
    const line = document.createElement("p");
    line.textContent = `${label}: ${utils.ATTRIBUTES.map((attribute) => `${attribute} ${recipe?.[attribute] ?? "?"}`).join(" | ")}`;
    return line;
  }

  async function reviewFeedback(id, decision) {
    try {
      const response = await fetch(`${API_BASE_URL}/api/feedback/${encodeURIComponent(id)}/${decision}`, { method: "POST" });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || `HTTP ${response.status}`);
      recordEvent(decision === "approve" ? "feedback_approved" : "feedback_rejected", { id });
      await loadFeedbackQueue();
    } catch (error) {
      feedbackQueue.textContent = `Could not review this correction: ${error.message}`;
    }
  }

  async function loadFeedbackQueue() {
    try {
      const response = await fetch(`${API_BASE_URL}/api/feedback?status=pending`);
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || `HTTP ${response.status}`);
      feedbackQueue.replaceChildren();
      if (!body.entries.length) {
        const empty = document.createElement("p");
        empty.textContent = "No pending corrections. Submitted examples will appear here for review.";
        feedbackQueue.appendChild(empty);
        return;
      }
      body.entries.forEach((entry) => {
        const card = document.createElement("article");
        card.className = "lab-feedback-card";
        const title = document.createElement("h4");
        title.textContent = `${utils.MODEL_LABELS[entry.model] || entry.model} | Priority ${entry.priority}`;
        card.append(title);
        const request = document.createElement("blockquote");
        request.textContent = entry.text;
        card.append(request, makeRecipeLine("Predicted", entry.predicted), makeRecipeLine("Corrected", entry.corrected));
        const changed = changedAttributes(entry.predicted, entry.corrected);
        const metadata = document.createElement("p");
        const confidenceText = entry.confidence
          ? utils.ATTRIBUTES.map((attribute) => `${attribute}: ${entry.confidence[attribute] == null ? "n/a" : `${(entry.confidence[attribute] * 100).toFixed(1)}%`}`).join(" | ")
          : "Confidence unavailable";
        metadata.textContent = `Changed: ${changed.join(", ")} | ${confidenceText} | ${new Date(entry.created_at).toLocaleString()}${entry.model_disagreement ? " | Model disagreement" : ""}${entry.low_confidence ? " | Low confidence" : ""}`;
        card.appendChild(metadata);
        const actions = document.createElement("div");
        actions.className = "lab-feedback-actions";
        [["Approve", "approve"], ["Reject", "reject"]].forEach(([label, decision]) => {
          const button = document.createElement("button");
          button.type = "button";
          button.className = decision === "approve" ? "primary-btn" : "secondary-btn";
          button.textContent = label;
          button.addEventListener("click", () => reviewFeedback(entry.id, decision));
          actions.appendChild(button);
        });
        card.appendChild(actions);
        feedbackQueue.appendChild(card);
      });
    } catch (error) {
      feedbackQueue.textContent = `Feedback queue unavailable: ${error.message}`;
    }
  }

  async function analyzeRequest() {
    const payload = utils.createAnalysisPayload(requestInput.value, getExpectedRecipe());
    if (!payload.text) {
      statusEl.textContent = "Enter a customer request before analyzing.";
      requestInput.focus();
      return;
    }
    analyzeBtn.disabled = true;
    latestComparison = null;
    correctionPanel.classList.add("hidden");
    statusEl.textContent = "Running the request through available models...";
    recordEvent("ai_lab_analysis_started", { hasGroundTruth: Boolean(payload.ground_truth) });
    try {
      const response = await fetch(`${API_BASE_URL}/api/lab/compare`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || `HTTP ${response.status}`);
      const result = utils.normalizeComparisonResponse(body);
      result.ground_truth = payload.ground_truth;
      latestComparison = result;
      const failures = utils.MODEL_ORDER.filter((name) => !result.models[name].available);
      recordEvent("ai_lab_analysis_run", {
        hasGroundTruth: Boolean(payload.ground_truth),
        model_count: utils.MODEL_ORDER.length - failures.length,
        disagreement_count: utils.findDisagreements(result.models).length,
      });
      failures.forEach((model) => recordEvent("ai_lab_model_failure", { model, error: result.models[model].error }));
      renderResults(result, payload.ground_truth);
      prefillCorrection();
      statusEl.textContent = failures.length
        ? `Analysis complete; ${failures.length} model(s) unavailable. See row details.`
        : payload.ground_truth
          ? "Analysis complete. Attribute labels are compared with the supplied expected recipe."
          : "Analysis complete. No ground truth supplied; disagreements do not indicate correctness.";
    } catch (error) {
      resultBody.replaceChildren();
      const row = document.createElement("tr");
      const message = document.createElement("td");
      message.colSpan = 8;
      message.textContent = `Could not analyze this request: ${error.message}`;
      row.appendChild(message);
      resultBody.appendChild(row);
      disagreementEl.replaceChildren();
      confidenceContentEl.replaceChildren();
      latestComparison = null;
      correctionPanel.classList.add("hidden");
      statusEl.textContent = `AI Lab request failed: ${error.message}`;
    } finally {
      analyzeBtn.disabled = false;
    }
  }

  function loadSelectedRobustnessExample() {
    const records = examplesByCategory.get(exampleCategory.value) || [];
    const record = records[Number(exampleSelect.value)];
    const selected = utils.getExampleInput(record);
    if (!selected) return;
    requestInput.value = selected.text;
    latestComparison = null;
    correctionPanel.classList.add("hidden");
    if (selected.groundTruth) setExpectedRecipe(selected.groundTruth);
    recordEvent("ai_lab_example_loaded", { source: "robustness", category: record.category });
    statusEl.textContent = `Loaded labeled ${record.category} example. Expected recipe is provided from the dataset.`;
  }

  function generateDifficultyExample() {
    const recipe = {
      base: "espresso",
      milk: "oat milk",
      sweetness: "light sugar",
      topping: "boba",
      vibe: "cozy",
    };
    const generated = window.BrewAIPersonas.generateCustomerOrder(
      recipe,
      "coffee_snob",
      window.BrewAIPersonas.createSeededRandom(nextSeed++),
      difficultySelect.value,
    );
    requestInput.value = generated.request;
    latestComparison = null;
    correctionPanel.classList.add("hidden");
    setExpectedRecipe(recipe);
    recordEvent("ai_lab_example_loaded", { source: "difficulty", difficulty: difficultySelect.value });
    statusEl.textContent = `Generated ${difficultySelect.value} diagnostic wording. Known canonical recipe is supplied as expected output.`;
  }

  async function compareCustomerGeneration() {
    const recipe = Object.fromEntries([...document.querySelectorAll("[data-generation-recipe]")]
      .map((select) => [select.dataset.generationRecipe, select.value]));
    const personaId = document.getElementById("lab-generation-persona").value;
    const persona = window.BrewAIPersonas.PERSONAS[personaId];
    const difficulty = document.getElementById("lab-generation-difficulty").value;
    const template = window.BrewAIPersonas.generateCustomerOrder(
      recipe, personaId, window.BrewAIPersonas.createSeededRandom(2718), difficulty,
    );
    generationCompareBtn.disabled = true;
    generationComparisonEl.textContent = "Comparing template with local generation...";
    try {
      const result = await window.BrewAICustomerGeneration.compare({
        canonical_recipe: recipe, persona: { ...persona }, difficulty, template_request: template.request,
      });
      const templateValidation = result?.template?.validation;
      const local = result?.local_ai;
      generationComparisonEl.replaceChildren();
      const rows = [
        ["Template", result?.template?.request || template.request,
          templateValidation?.valid ? "Valid" : `Validation: ${(templateValidation?.issues || ["unavailable"]).join(", ")}`],
        [local?.source === "local_ai" ? `Ollama (${local.model || "local model"})` : "Ollama fallback",
          local?.request || "No validated local response; use the template.",
          local?.success ? `Valid | ${local.latency_ms} ms | cache ${local.cache_hit ? "hit" : "miss"}`
            : `Fallback: ${local?.fallback_reason || "backend unavailable"}`],
      ];
      rows.forEach(([label, text, detail]) => {
        const card = document.createElement("p");
        card.textContent = `${label}: ${text} (${detail})`;
        generationComparisonEl.appendChild(card);
      });
    } catch (_error) {
      generationComparisonEl.textContent = "Comparison unavailable. Template generation remains available without Ollama.";
    } finally {
      generationCompareBtn.disabled = false;
    }
  }

  function open() {
    aiLabEl.classList.remove("hidden");
    gameGridEl.classList.add("hidden");
    overlayEl.classList.add("hidden");
    modeButton.classList.add("active");
    document.getElementById("game-mode-btn").classList.remove("active");
    document.getElementById("rush-hour-mode-btn").classList.remove("active");
    recordEvent("ai_lab_opened");
    loadBenchmarkSummary();
    if (!examplesByCategory.size) loadRobustnessExamples();
    loadFeedbackQueue();
  }

  function close() {
    aiLabEl.classList.add("hidden");
    gameGridEl.classList.remove("hidden");
    overlayEl.classList.remove("hidden");
    modeButton.classList.remove("active");
    const gameMode = document.getElementById("game-mode-btn");
    const rushMode = document.getElementById("rush-hour-mode-btn");
    (window.BrewAIGameMode === "rush_hour" ? rushMode : gameMode).classList.add("active");
  }

  modeButton.addEventListener("click", open);
  document.getElementById("lab-back-btn").addEventListener("click", close);
  analyzeBtn.addEventListener("click", analyzeRequest);
  exampleCategory.addEventListener("change", populateExampleOptions);
  exampleSelect.addEventListener("change", loadSelectedRobustnessExample);
  loadExampleBtn.addEventListener("click", loadSelectedRobustnessExample);
  generateDifficultyBtn.addEventListener("click", generateDifficultyExample);
  generationCompareBtn.addEventListener("click", compareCustomerGeneration);
  correctionModel.addEventListener("change", prefillCorrection);
  correctionSubmit.addEventListener("click", submitCorrection);
  feedbackRefresh.addEventListener("click", loadFeedbackQueue);
  requestInput.addEventListener("input", () => {
    latestComparison = null;
    correctionPanel.classList.add("hidden");
  });
  groundTruthToggle.addEventListener("change", () => {
    groundTruthFields.classList.toggle("hidden", !groundTruthToggle.checked);
  });
  document.querySelectorAll(".lab-prompt").forEach((button) => {
    button.addEventListener("click", () => {
      const prompts = {
        normal: "I'd like an espresso with oat milk, light sugar, boba, and a cozy vibe.",
        slang: "Need a strong espresso, oat milk, just a lil sweet, boba, chill vibe.",
        negation: "Espresso, not almond milk but oat milk, no sugar, not boba but coffee jelly, classic.",
        ambiguity: "Something creamy and slightly sweet, maybe with a fun topping.",
        multi_clue: "I need something strong but smooth, oat milk, not too sweet, and cinnamon would be nice.",
      };
      setFreeFormRequest(prompts[button.dataset.example]);
      recordEvent("ai_lab_example_loaded", { source: "prompt", example: button.dataset.example });
    });
  });

  window.BrewAILab = { open, close, events: window.BrewAILabEvents };
})();
