# Sarkari Match (working name)

Which Indian government jobs can you actually apply for? Official notification PDFs go in, validated structured records come out, and a rules engine answers the question with the reason behind every verdict.

```
pipeline/   discover official PDFs -> pdfplumber -> Gemini structured output -> validation gate -> data/notifications.json
engine/     eligibility rules (pure functions, unit tested)
evals/      extraction accuracy against a hand-labelled gold set; matcher precision/recall against judged profiles
web/        FastAPI + Jinja: matcher, one page per notification / board / qualification, sitemap, JSON-LD
scripts/    refresh.py (daily job), metrics_snapshot.py (case-study numbers), predict_gold.py
docs/       CASE_STUDY.md template, METRICS.md, metrics-log.csv
```

## Run locally
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env            # add GEMINI_API_KEY (free tier is enough)
.venv/bin/python -m pytest -q tests
.venv/bin/python evals/run_extraction_eval.py
.venv/bin/python evals/run_matcher_eval.py
.venv/bin/uvicorn web.app:app --reload --port 8010
```
The site ships with six hand-written sample notifications so it runs with no key. They are flagged `is_sample` and a banner says so. Replace them with real data:
```bash
.venv/bin/python scripts/refresh.py --dry-run     # discover + download only, check what the sources yield
.venv/bin/python scripts/refresh.py --limit 10    # extract with Gemini, validate, store
```

## Paid alerts (the revenue line)
`/alerts` sells an email alert pass: ₹99 for 180 days by default. Every refresh, each active subscriber's profile is matched against new open notifications and they get one email listing only the posts they are eligible for, with a manage/stop link.

- Payment: Razorpay checkout; `POST /api/alerts/order` creates the order, `POST /api/alerts/verify` checks the HMAC signature and activates the pass. With no keys set the page runs in demo mode and activates for free.
- Delivery: Resend (`RESEND_API_KEY`, `ALERT_FROM`); without a key emails are printed to the log.
- Dispatch: `scripts/send_alerts.py` locally, or `POST /api/alerts/dispatch` with `Authorization: Bearer $ALERTS_CRON_SECRET`. The daily workflow calls it when the `ALERTS_DISPATCH_URL` and `ALERTS_CRON_SECRET` secrets are set.
- Storage: `data/subscribers.json` (gitignored, holds emails). On hosts with ephemeral disks set `SUBSCRIBERS_FILE` to a persistent path.

## Free-tier budget
- Gemini: one call per new PDF, capped at 10 per run. Nothing is re-extracted unless you ask.
- Hosting: any free Python host. The data file is committed, so the app has no database to pay for.
- Refresh: GitHub Actions cron, commits `data/notifications.json` daily.

## Building the case study
1. Label 50 real notifications into `evals/gold/` (one day). Run `scripts/predict_gold.py`, then the extraction eval. That first number is your baseline.
2. Improve the prompt, re-run, log. `docs/metrics-log.csv` accumulates the story.
3. Launch, submit the sitemap, and enter Search Console numbers weekly.
4. Fill `docs/CASE_STUDY.md`. Every TODO maps to a number the repo already produces.

## Scope choices
- Official sources only. No aggregator scraping, no captcha bypass.
- Records with soft validation failures are held in `/admin/review`, never published silently.
- Rules default to central government relaxations only when the notification is silent; stated values always win.
