# BrewAI Case Study

## Product Management

### Problem and target experience

The goal was to make NLP behavior tangible rather than present a prediction dashboard alone. Players should interpret a customer request, choose how much help to use, and feel consequences for speed and correctness. The primary user is a student or demo reviewer exploring applied NLP through a short game.

### Product hypothesis and gameplay decisions

If requests vary by persona and difficulty, and uncertainty creates an ASK-versus-GUESS choice, a player can understand the model's role through play. Clarification spends time; hints spend score; both reveal canonical truth at controlled levels. Rush Hour uses a small fixed queue rather than a complex simulation.

### Instrumentation and experiments

The app records anonymous local gameplay events and supports deterministic per-session experiment assignments. Metrics cover order outcomes, response time, hint/clarification usage, model disagreement, and policy behavior. No user study or experiment result is claimed here; small samples are explicitly exploratory.

### Metrics and tradeoffs

Product measures include completion, order correctness, response time, customer loss, and support-mechanic use. These are telemetry definitions, not validated proxies for enjoyment. The system favors short understandable rounds over realistic cafe operations and local persistence over hosted analytics.

### Iteration

The project evolved from a parser demonstration into Game Mode and Rush Hour, then added personas, attribute confidence, clarification, progressive hints, feedback review, analytics, and local dialogue fallback. These iterations establish scope and testability, not product-market fit.

## AI Engineering

### Dataset and baseline

The canonical labeled dataset has 200 records and five categorical targets. A reproducible production run hashes the dataset, forms the existing 0.55 character n-gram similarity groups, makes a seeded grouped holdout (149 train / 51 holdout), and fits calibrated TF-IDF/Logistic Regression only on the training side. The saved metadata includes split parameters and per-attribute macro F1.

### Evaluation and model choice

The separate model comparison evaluated keyword rules, Multinomial Naive Bayes, Logistic Regression, and Linear SVM. Its report shows Linear SVM at 0.977 average macro F1 on that grouped holdout. The current production run's calibrated Logistic Regression scores 0.929 macro F1 on the same split procedure. Production remains Logistic Regression because the game consumes probability estimates; the compared Linear SVM is not calibrated. Comparing calibrated alternatives is future work.

### Uncertainty and ground truth

Each attribute exposes a probability-based score from the production classifier. No formal reliability-diagram/ECE evaluation currently supports a claim that confidence is perfectly calibrated. The canonical recipe is independent of model output, allowing player and model results to be evaluated without circularly treating a prediction as truth.

### Feedback and candidate retraining

Corrections enter a pending SQLite queue and require explicit review. Candidate retraining validates labels, excludes holdout-text leakage, compares against a baseline and no-feedback control, and writes a separate candidate artifact. There is no automatic training or promotion.

### Contextual bandit and local generation

The contextual bandit uses a small normalized state, bounded difficulty actions, and an explicit hand-designed reward. It is an online contextual bandit, not deep reinforcement learning; its weights/reward do not establish user learning. Optional local Ollama generates customer wording from canonical attributes. Validators reject contradictions and incomplete attribute wording, and templates handle unavailable/invalid output.

### What remains limited

Dataset size and provenance limit external validity. Similarity grouping reduces near-duplicate leakage but cannot remove all distribution bias. Ambiguity labels are reviewed interpretations, not uniquely objective answers. Production confidence needs dedicated calibration evaluation. No live player study establishes that hints, difficulty adaptation, or reward settings improve engagement.
