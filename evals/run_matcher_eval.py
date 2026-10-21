"""Precision and recall of the eligibility engine against hand-judged profiles."""
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine.eligibility import match_all  # noqa: E402
from engine.schema import CandidateProfile  # noqa: E402
from pipeline import store  # noqa: E402

ROOT = Path(__file__).resolve().parent
TODAY = date(2026, 10, 14)  # pinned so results are reproducible; expected lists were judged on this date


def main() -> int:
    notifs = store.load()
    profiles = json.loads((ROOT / "profiles.json").read_text())
    tp = fp = fn = 0
    for item in profiles:
        prof = CandidateProfile(**item["profile"])
        got = {f"{m.notification_slug}::{m.post_name}" for m in match_all(notifs, prof, TODAY) if m.eligible}
        exp = set(item["expected"])
        tp += len(got & exp)
        fp += len(got - exp)
        fn += len(exp - got)
        for key in sorted(got - exp):
            print(f"[{item['id']}] FALSE POSITIVE {key}")
        for key in sorted(exp - got):
            slug, post = key.split("::")
            why = [r.detail for m in match_all(notifs, prof, TODAY) if m.notification_slug == slug and m.post_name == post for r in m.reasons if not r.passed]
            print(f"[{item['id']}] FALSE NEGATIVE {key}  engine says: {why}")
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    print(f"\nprofiles={len(profiles)} tp={tp} fp={fp} fn={fn}  precision={precision:.1%} recall={recall:.1%}")
    out = ROOT / "results" / f"matcher-{date.today().isoformat()}.json"
    out.write_text(json.dumps({"date": date.today().isoformat(), "profiles": len(profiles), "tp": tp, "fp": fp, "fn": fn,
                               "precision": round(precision, 3), "recall": round(recall, 3)}, indent=2))
    print(f"wrote {out.relative_to(ROOT.parent)}")
    return 0 if fp == 0 and fn == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
