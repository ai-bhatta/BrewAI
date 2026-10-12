# BrewAI Architecture

```mermaid
flowchart TB
  Browser[Browser Frontend\nGame, AI Lab, Analytics]
  API[FastAPI Backend]
  Parser[Order Parser\nRules / Production Model]
  Lab[AI Lab\ncomparison candidates]
  Feedback[Human-Reviewed Feedback]
  Analytics[Analytics and Experiments]
  Bandit[Adaptive Difficulty\nHeuristic / Contextual Bandit]
  Canonical[Canonical Dataset]
  Production[Versioned Production Artifact]
  DB1[(Feedback SQLite)]
  DB2[(Analytics SQLite)]
  DB3[(Bandit SQLite)]
  DB4[(Generation Cache SQLite)]
  Ollama[Optional loopback Ollama]
  Generation[Validated Customer Dialogue]

  Browser <--> API
  API --> Parser
  API --> Lab
  API --> Feedback
  API --> Analytics
  API --> Bandit
  Parser --> Production
  Canonical --> Production
  Canonical --> Lab
  Feedback --> DB1
  Analytics --> DB2
  Bandit --> DB3
  API --> DB4
  Ollama -. optional .-> Generation
  Generation -. validated output .-> Browser
```

The browser owns round and shift interaction. The API predicts attributes independently and evaluates player submissions against canonical ground truth. SQLite is local and separated by concern. The production model, AI Lab comparison models, and human-feedback candidates have separate artifacts/provenance; candidates are not automatically promoted. Optional customer generation receives canonical attributes and must pass validation before use.
