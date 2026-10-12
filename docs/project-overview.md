# Project Overview

## Title

`BrewAI: Natural-Language Drink Parsing in a Browser-Based Barista Game`

## Problem

The parser maps a natural-language cafe request into five categorical drink attributes: base, milk, sweetness, topping, and vibe. The game makes those outputs observable while keeping canonical ground truth separate for independent scoring.

## Components

- `frontend/`: Game Mode, Rush Hour, personas, uncertainty/help mechanics, AI Lab, and local analytics.
- `backend/`: FastAPI inference/evaluation, feedback review, analytics, adaptive policy, and optional customer wording generation.
- `ml/`: reproducible production training, model comparison, candidate evaluation, and policy simulation.
- `data/`: the canonical labeled dataset and explicit local configuration.
- `results/`: grouped evaluation reports and model provenance metadata.

## Reproducibility

The current production artifact is calibrated Logistic Regression fitted on 149 records from a deterministic similarity-grouped split; its 51-record holdout is not used for fitting. The artifact is intentionally generated locally and ignored by version control. Rebuild it with `python ml/train_production_model.py`. The Linear SVM benchmark result is a separate grouped-holdout comparison, not the model currently served.

## Evaluation Caveats

The 200-record dataset is small, and its provenance is not an independently validated population sample. The grouped split reduces near-duplicate leakage, but does not establish real-world accuracy. Probability confidence has not received a formal reliability-curve evaluation. Ambiguous examples use reviewed interpretations rather than uniquely objective labels.
