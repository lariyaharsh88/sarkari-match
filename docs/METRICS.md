# What to measure, and when

The case study is only credible if every number has a date and a source. Log weekly.

| Metric | Source | How |
|---|---|---|
| Extraction accuracy, per field | `evals/run_extraction_eval.py` | Re-run after every prompt or model change. Keep the gold set frozen. |
| Matcher precision and recall | `evals/run_matcher_eval.py` | Re-run whenever a rule changes. Add a profile for every bug report. |
| Notifications live, posts, boards | `scripts/metrics_snapshot.py` | Automatic, daily in CI. |
| Rejected / held for review | refresh logs | Count per week; it is the story of the validation gate. |
| Pages indexed, clicks, impressions | Google Search Console | Enter by hand into `docs/metrics-log.csv` weekly. |
| Eligibility checks | server logs or a counter on POST /match | Add a one-line counter before launch. |

Baseline week: label 50 notifications, run the first eval with the first prompt, and record that number before improving anything. The before/after is the case study.
