# AI System Flow

```mermaid
flowchart TD
  Recipe[Canonical Recipe] --> Wording[Persona + Difficulty]
  Wording --> Generator[Deterministic Template / Optional Local AI]
  Generator --> Validate[Validate all canonical attributes]
  Validate --> Request[Customer Request]
  Request --> Parser[NLP Parser]
  Parser --> Prediction[Attribute Prediction + Confidence]
  Prediction --> Player{Player Decision}
  Player -->|Spend score| Hint[Progressive Hint]
  Player -->|Spend time| Clarify[Canonical Attribute Clarification]
  Player --> Build[Build and Serve Drink]
  Hint --> Build
  Clarify --> Build
  Build --> Compare[Compare with Canonical Ground Truth]
  Compare --> Score[Score and Feedback]
  Score --> Events[Anonymous Local Analytics]
  Events --> Difficulty[Heuristic / Contextual Bandit]
  Difficulty --> Wording
  Validate -. invalid or unavailable .-> TemplateFallback[Use Template]
  TemplateFallback --> Request
```

The parser prediction never replaces canonical ground truth. Hints and clarification read canonical values, and evaluation scores the submitted drink against those values. Generation is optional and does not use a cloud service.
