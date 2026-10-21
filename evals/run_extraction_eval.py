"""Compare predictions against gold, field by field."""
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine.schema import Notification  # noqa: E402

ROOT = Path(__file__).resolve().parent
TOP_FIELDS = ["title", "advt_no", "apply_start", "apply_end", "total_vacancies", "fee_by_category"]
POST_FIELDS = ["vacancies", "pay_level", "min_qualification", "required_streams", "gender_restriction", "states"]
AGE_FIELDS = ["min_age", "max_age", "as_on", "relaxation_years"]


def norm(v):
    if isinstance(v, list):
        return sorted(str(x).lower() for x in v)
    if isinstance(v, dict):
        return {str(k).upper(): v[k] for k in v}
    if isinstance(v, str):
        return " ".join(v.lower().split())
    return v


def main() -> int:
    gold_files = sorted((ROOT / "gold").glob("*.json"))
    if not gold_files:
        print("no gold files")
        return 1
    hits = defaultdict(int)
    totals = defaultdict(int)
    misses = []
    missing_predictions = 0
    for gf in gold_files:
        pf = ROOT / "predictions" / gf.name
        if not pf.exists():
            missing_predictions += 1
            continue
        g = Notification(**json.loads(gf.read_text()))
        p = Notification(**json.loads(pf.read_text()))
        for f in TOP_FIELDS:
            totals[f] += 1
            if norm(getattr(g, f)) == norm(getattr(p, f)):
                hits[f] += 1
            else:
                misses.append((g.slug, f, getattr(g, f), getattr(p, f)))
        gposts = {norm(x.post_name): x for x in g.posts}
        pposts = {norm(x.post_name): x for x in p.posts}
        totals["post_names"] += 1
        if set(gposts) == set(pposts):
            hits["post_names"] += 1
        else:
            misses.append((g.slug, "post_names", sorted(gposts), sorted(pposts)))
        for name, gp in gposts.items():
            pp = pposts.get(name)
            for f in POST_FIELDS:
                totals[f"post.{f}"] += 1
                if pp is not None and norm(getattr(gp, f)) == norm(getattr(pp, f)):
                    hits[f"post.{f}"] += 1
                else:
                    misses.append((g.slug, f"{name}.{f}", getattr(gp, f), getattr(pp, f) if pp else None))
            for f in AGE_FIELDS:
                totals[f"post.age.{f}"] += 1
                if pp is not None and norm(getattr(gp.age, f)) == norm(getattr(pp.age, f)):
                    hits[f"post.age.{f}"] += 1
                else:
                    misses.append((g.slug, f"{name}.age.{f}", getattr(gp.age, f), getattr(pp.age, f) if pp else None))

    report = {k: round(hits[k] / totals[k], 3) for k in totals}
    overall = round(sum(hits.values()) / max(1, sum(totals.values())), 3)
    print(f"{'field':28} {'acc':>6}  {'n':>4}")
    for k in sorted(report, key=report.get):
        print(f"{k:28} {report[k]:6.1%}  {totals[k]:4}")
    print(f"\noverall field accuracy: {overall:.1%} over {len(gold_files) - missing_predictions} notifications")
    if missing_predictions:
        print(f"({missing_predictions} gold files have no prediction yet)")
    if misses:
        print("\nmisses:")
        for slug, f, gv, pv in misses[:40]:
            print(f"  {slug} {f}: gold={gv!r} pred={pv!r}")
    out = ROOT / "results" / f"extraction-{date.today().isoformat()}.json"
    out.write_text(json.dumps({"date": date.today().isoformat(), "notifications": len(gold_files) - missing_predictions,
                               "overall": overall, "per_field": report, "misses": len(misses)}, indent=2))
    print(f"\nwrote {out.relative_to(ROOT.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
