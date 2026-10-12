# Model Comparison Results

- Dataset records: `200`
- Split: `StratifiedGroupKFold by base label; character n-gram similarity groups`
- Train/test: `149/51`
- Similarity threshold: `0.55`
- Maximum train/test similarity: `0.541`
- Robustness examples: `35`
- Best grouped-holdout model: `linear_svm`

## Grouped Holdout Comparison

| Model | Avg Accuracy | Avg Macro F1 | Mean Latency / Order (ms) | P95 Latency / Order (ms) |
| --- | ---: | ---: | ---: | ---: |
| keyword_rules | 0.663 | 0.567 | 0.118 | 0.176 |
| multinomial_nb | 0.859 | 0.855 | 3.865 | 6.326 |
| logistic_regression | 0.929 | 0.925 | 3.559 | 5.462 |
| linear_svm | 0.980 | 0.977 | 3.312 | 5.178 |

## Per-Attribute Macro F1

| Attribute | keyword_rules | multinomial_nb | logistic_regression | linear_svm |
| --- | ---: | ---: | ---: | ---: |
| base | 0.923 | 1.000 | 1.000 | 1.000 |
| milk | 0.661 | 0.877 | 0.920 | 0.978 |
| sweetness | 0.172 | 0.825 | 0.901 | 0.979 |
| topping | 0.602 | 0.696 | 0.886 | 0.950 |
| vibe | 0.477 | 0.877 | 0.920 | 0.978 |

## Robustness Categories

| Category | keyword_rules | multinomial_nb | logistic_regression | linear_svm |
| --- | ---: | ---: | ---: | ---: |
| ambiguity | 0.468 | 0.265 | 0.233 | 0.233 |
| negation | 0.660 | 0.390 | 0.500 | 0.533 |
| normal | 0.805 | 0.573 | 0.650 | 0.650 |
| out_of_distribution | 0.570 | 0.717 | 0.850 | 0.850 |
| paraphrase | 0.333 | 0.515 | 0.607 | 0.665 |
| slang | 0.642 | 0.658 | 0.658 | 0.650 |
| typo | 0.767 | 0.590 | 0.650 | 0.667 |

Confusion matrices, per-class precision/recall/F1, per-category attribute metrics, and latency details are in `model_comparison.json`.
Ambiguity examples use a reviewed expected interpretation for diagnostic scoring; ambiguous language does not have a uniquely objective target.
