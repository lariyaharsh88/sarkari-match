# Evals

Two numbers drive the case study. Both are produced here, on demand, and logged to `results/`.

## 1. Extraction accuracy (`run_extraction_eval.py`)
- `gold/<slug>.json`: a hand-labelled `Notification`. Label 50 real notifications by reading the PDF yourself. This is the single most valuable day of work in the project.
- `predictions/<slug>.json`: what `pipeline.extract` produced for the same PDF. Regenerate with `scripts/predict_gold.py` after any prompt or model change.
- Output: per-field accuracy, worst fields, and an overall score. Appended to `results/extraction-<date>.json`.

## 2. Matcher precision and recall (`run_matcher_eval.py`)
- `profiles.json`: candidate profiles with the post keys (`slug::post_name`) a human says they are eligible for.
- Output: precision, recall, and every mismatch with the engine's reason, so a wrong rule is a one-line fix.

The sample gold and prediction files are there only to show the harness working. Replace them with real labelled data before quoting any number.
