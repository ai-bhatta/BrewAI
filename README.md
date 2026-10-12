# BrewAI

BrewAI is a cafe game where you read customer orders, make the right drinks, and race to serve them before time runs out. AI helps interpret each order, while you decide whether to trust its prediction, ask the customer, or use a hint.

![BrewBot pixel-art avatar](Avatar_1.png)

> BrewAI is a local-first academic portfolio project. Gameplay works without a trained model or Ollama, using the keyword/template fallbacks.

## Why I built it

I wanted an AI project where model behavior has a visible consequence. A request is parsed into a canonical drink recipe, uncertainty becomes a player decision, and a correct drink is scored independently of the model's prediction.

## Gameplay

- **Game Mode:** serve orders during a timed round; solo or two-player.
- **Rush Hour:** serve or lose five customers in a shift.
- **Progressive hints:** Nudge, Strong Hint, and Reveal spend points.
- **Clarification:** ask about the least-confident attribute and spend time.
- **Difficulty:** fixed, heuristic-adaptive, or contextual-bandit policy.

## AI Architecture

Five independent text classifiers predict `base`, `milk`, `sweetness`, `topping`, and `vibe`. Production uses calibrated Logistic Regression probabilities for the gameplay confidence display. The hidden canonical recipe remains ground truth; the model prediction never changes the correct answer.

The optional dialogue generator uses a locally installed Ollama model over loopback only. It is not an order parser or source of truth: generated dialogue is validated against the canonical recipe, and template wording is used when the model is unavailable or output fails validation.

## Product Architecture

The browser owns interaction and gameplay state. FastAPI provides model inference, evaluation, AI Lab, feedback review, analytics, adaptive-policy, and customer-generation endpoints. Local SQLite repositories persist analytics, reviewed feedback, bandit state, and validated generation cache.

See [Architecture](docs/architecture.md) and [AI System Flow](docs/ai-system-flow.md).

## Key Features

- Five-label natural-language order parsing and per-attribute confidence.
- Five structured customer personas with deterministic template wording.
- Player-facing uncertainty, clarification, and progressive hint mechanics.
- AI Lab comparison, explicitly reviewed correction queue, and isolated candidate retraining.
- Descriptive local analytics and deterministic A/B assignments.
- Optional local Ollama dialogue with validation and template fallback.

## AI / ML Systems

- **Supervised NLP:** TF-IDF word n-grams with per-attribute Logistic Regression; model families are compared offline.
- **Uncertainty:** calibrated classifier probabilities are displayed by attribute. Formal calibration plots/metrics are not yet included.
- **Human feedback:** corrections remain pending until a person approves them; candidates are evaluated separately and never auto-promoted.
- **Contextual bandit:** a small local epsilon-greedy linear reward policy chooses among nearby difficulty levels. This is not deep reinforcement learning and is not evidence that the system learns a person reliably.
- **Local generation:** optional Ollama dialogue is constrained by canonical attributes and never sends requests to a cloud API.

## Product Systems

Local analytics record anonymous gameplay and model events. Experiment assignments are stable per browser session. Metrics are descriptive; small samples are exploratory and do not establish causal impact. Adaptive difficulty has a fixed heuristic baseline and an optional contextual bandit policy.

## Model Evaluation

The canonical dataset contains 200 labeled utterances. The reproducible production run uses a deterministic, similarity-grouped holdout: 149 examples for training and 51 held out. The latest clean production run reports **0.929 average per-attribute macro F1** on that grouped holdout. This metric describes this split only, not general accuracy.

The separate model comparison reports **Linear SVM as the benchmark winner at 0.977 average macro F1** on its grouped holdout. Production remains **calibrated Logistic Regression** because the game consumes probability outputs; the current Linear SVM comparison model does not expose calibrated probabilities. This is a design tradeoff, not a claim that the production model is superior. A calibrated SVM is a future evaluation candidate, not an automatic replacement.

The fixed challenge set is diagnostic and is not used for production fitting. Ambiguity examples have reviewed expected interpretations, but ambiguity has no uniquely objective label. Historical `baseline_metrics.json` uses an older, non-grouped split and is retained as a legacy artifact; do not compare it directly with grouped-holdout results.

Recreate the production artifact and metadata:

```powershell
python ml/train_production_model.py
```

This hashes `data/order_dataset.json`, fits only the training side, scores the untouched grouped holdout, then writes the ignored model binary to `backend/model/order_parser.joblib` and provenance to `results/production_model_metadata.json`.

## Architecture

See the editable [system architecture diagram](docs/architecture.md) and [AI order-flow diagram](docs/ai-system-flow.md).

## Tech Stack

- Python 3.11+, FastAPI, scikit-learn, joblib, SQLite
- HTML, CSS, vanilla JavaScript
- Node.js 22+ and Playwright for optional end-to-end browser tests
- Docker Compose for the optional local container setup

## Run Locally

### Requirements

- Python 3.11 or newer.
- `uv` (recommended; the repository includes `uv.lock`) or pip.
- A modern browser. Node.js 22+ is needed only for the optional Playwright browser tests.

No API key, cloud account, or `.env` file is required. The order parser and game run locally. Ollama is optional and only adds locally hosted customer dialogue; without it, BrewAI uses templates.

### Quick start with uv (PowerShell)

Run these commands from the repository root:

```powershell
uv sync
uv run python ml/train_production_model.py
```

Training creates or refreshes the local model file at `backend/model/order_parser.joblib` and its tracked provenance at `results/production_model_metadata.json`. Start the backend in **Terminal 1**:

```powershell
uv run python -m uvicorn main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
```

Start the frontend in **Terminal 2**, from the repository root:

```powershell
uv run python -m http.server 5500 --bind 127.0.0.1
```

Open <http://127.0.0.1:5500/frontend/>. Confirm the backend is ready at <http://127.0.0.1:8000/api/health>; API documentation is at <http://127.0.0.1:8000/docs>. Keep both terminals running while you play.

### pip alternative

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python ml/train_production_model.py
```

Then use the same two server commands above, replacing `uv run python` with `python`.

### Optional Docker setup

```powershell
docker compose up --build
```

Open <http://127.0.0.1:8080/frontend/>. Docker builds the production model from the included dataset and persists SQLite/config data in the `brewai_data` volume. Docker is optional; the two-terminal setup above is the recommended way to start testing the app. Optional generation uses templates unless Ollama is reachable from the backend's own loopback.

## Optional Ollama Setup

This is optional; no API key is involved. Install Ollama yourself and make its local service available at `http://127.0.0.1:11434`, then pull the configured model (`qwen3:4b` by default). BrewAI never downloads a model. `auto` mode attempts local generation and safely falls back to templates. Set `mode` to `templates` to avoid model calls, or `local_ai` to explicitly request local dialogue. AI Lab reports model/validation fallback details.

Optional local AI smoke test:

```powershell
uv run python scripts/ollama_smoke_test.py
```

The smoke test checks reachability, exact configured model availability, validated generation or safe fallback, and local cache behavior. It is not part of regular tests.

## Testing

### Play the game manually

1. Start the backend and frontend using the two-terminal quick start.
2. Open <http://127.0.0.1:5500/frontend/> and enter a player name.
3. Choose Game Mode or Rush Hour, set the difficulty, then start the round or shift.
4. Try an order, inspect per-attribute confidence, ask for clarification or use a hint, build the drink, and serve it before the timer expires.
5. In Rush Hour, complete orders or let customer timers expire, then inspect the shift summary.
6. Open AI Lab or Analytics from the interface to explore model comparison, feedback review, and local event summaries.

Run the non-browser automated suites from the project root:

```powershell
uv run python -m unittest discover -s tests -v
node --test tests/*.test.js
```

Run syntax/health checks:

```powershell
uv run python -m compileall -q backend ml scripts tests
node --check frontend/app.js
node --check frontend/ai_lab.js
uv run python scripts/health_check.py
```

Optional real-browser suite (Chromium; no Ollama required):

```powershell
npm install
npm run install:e2e-browser
# In separate terminals, start the backend and frontend using the commands above.
npm run test:e2e
```

Playwright uses the running local backend and static server; test API routes are stubbed to keep tests deterministic and prevent database mutation. The browser suite covers Game Mode scoring, clarification cost, hint progression, Rush Hour completion, AI Lab analysis/feedback, and analytics rendering.

Capture the portfolio screenshots with the same fixture-backed browser states:

```powershell
npm run capture:screenshots
```

## Project Structure

```text
backend/       FastAPI services, model loading, local SQLite repositories
data/          Canonical labeled data and local feature configuration
docs/          Architecture, demo, case study, interview, and release materials
frontend/      Browser game, AI Lab, analytics, and gameplay mechanics
ml/            Production training, model comparison, evaluation, simulations
results/       Evaluation reports and tracked model provenance metadata
scripts/       Health and optional local Ollama checks
tests/         Python/JavaScript unit tests and Playwright E2E tests
```

## Limitations

- The dataset is small and its collection process is not an independently validated sample of real cafe requests.
- Grouped holdout reduces near-duplicate leakage but does not guarantee performance on new populations or domains.
- Confidence values have not been assessed with reliability diagrams or expected calibration error.
- The contextual bandit's reward weights are hand-designed product choices; no user study establishes that they optimize enjoyment.
- Playwright tests use mocked API responses; they verify browser integration, not live model quality. Run them with the documented Chromium install.
- Portfolio screenshots are fixture-backed browser renders, not evidence of live model quality. Review them at desktop/mobile widths and check for private information before publishing.

## Future Work

- Collect and independently review more diverse order examples.
- Evaluate probability calibration and a calibrated Linear SVM on the same frozen split.
- Run usability studies before drawing conclusions about difficulty or reward policy.
- Add real-user evidence only with consent.

## Project Documentation

- [Two-minute demo script](docs/demo_script.md)
- [Product and AI engineering case study](docs/case_study.md)
- [Release checklist](docs/release_checklist.md)
