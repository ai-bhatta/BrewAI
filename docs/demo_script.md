# BrewAI Demo Script (About 2:50)

## 0:00-0:20 | Introduce the experience

“BrewAI is a local-first barista game. A customer describes a drink in natural language; a multi-attribute parser predicts the recipe, while the player is scored against separate canonical ground truth.” Show the start screen and select a player name.

## 0:20-0:50 | Play an order

Start Game Mode and Begin Turn. Point out the persona badge, timer, recipe builder, score, and model confidence. Build a drink and serve it; mention the score reflects the submitted recipe, not whether the model guessed correctly.

## 0:50-1:10 | Show the decision mechanics

If the order exposes uncertainty, ask for clarification and point out the time cost. Use Nudge, Strong Hint, and Reveal in sequence to show progressive information and score cost. If the chosen order has no eligible uncertainty, use the next order; do not imply uncertainty is guaranteed for every request.

## 1:10-1:30 | Show adaptation

Describe the selected fixed/heuristic/bandit policy. Show the policy note and one or two orders. Explain that the contextual bandit is a small local policy over neighboring difficulty levels, not deep RL or proof of personalized learning.

## 1:30-1:55 | Compare models

Open AI Lab, load a labeled example, and Analyze. Point out per-attribute predictions, confidence where supported, disagreement, and the grouped-holdout comparison summary. State that agreement is not correctness when no expected recipe is provided.

## 1:55-2:15 | Human review

Change a prediction in the correction panel and submit it. Show the pending queue. Explain that feedback is not trained automatically: approval is explicit, candidate training is separate, and candidates are not production models.

## 2:15-2:35 | Product instrumentation

Open Analytics. Show engagement/gameplay metrics and experiment assignments. Note that these are local descriptive metrics and small samples are exploratory, not causal evidence.

## 2:35-2:50 | Close with engineering choices

Mention the 149/51 grouped production split and that the current production model is calibrated Logistic Regression while Linear SVM led the separate benchmark. Optional Ollama only generates constrained customer wording; without it, templates continue to work.
