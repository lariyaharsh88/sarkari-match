"""Append one row of product numbers to docs/metrics-log.csv. Run weekly (the CI workflow does).
Search Console numbers are entered by hand from the GSC UI (clicks, impressions, indexed pages)."""
import csv
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline import store  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "docs" / "metrics-log.csv"
items = store.load()
live = [n for n in items if not n.needs_review and not n.is_sample]
latest = {}
for kind in ("extraction", "matcher"):
    files = sorted((ROOT / "evals" / "results").glob(f"{kind}-*.json"))
    latest[kind] = json.loads(files[-1].read_text()) if files else {}
row = {
    "date": date.today().isoformat(),
    "notifications_live": len(live),
    "posts_live": sum(len(n.posts) for n in live),
    "boards": len({n.board for n in live}),
    "in_review": sum(1 for n in items if n.needs_review),
    "extraction_accuracy": latest["extraction"].get("overall", ""),
    "extraction_gold_n": latest["extraction"].get("notifications", ""),
    "matcher_precision": latest["matcher"].get("precision", ""),
    "matcher_recall": latest["matcher"].get("recall", ""),
    "gsc_clicks_28d": "", "gsc_impressions_28d": "", "gsc_pages_indexed": "", "eligibility_checks_28d": "",
}
new = not LOG.exists()
with LOG.open("a", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(row))
    if new:
        w.writeheader()
    w.writerow(row)
print(json.dumps(row, indent=2))
