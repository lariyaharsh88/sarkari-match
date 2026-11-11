"""Download real notification PDFs and write blank gold-label files to evals/gold/todo/.

Usage: python scripts/scaffold_gold.py [--n 50]
Open each PDF, fill its todo JSON, then move it to evals/gold/ (see evals/LABELLING.md).
Boards are round-robined so one site with hundreds of links cannot fill the whole set."""
import argparse
import json
import sys
from collections import defaultdict
from itertools import zip_longest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.fetch import discover, download_new, make_session, pdf_path_for  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TODO = ROOT / "evals" / "gold" / "todo"

POST = {
    "post_name": "",
    "vacancies": None,
    "vacancies_by_category": {},
    "pay_level": None,
    "min_qualification": "",
    "required_streams": [],
    "qualification_text": "",
    "age": {"min_age": None, "max_age": None, "as_on": None, "relaxation_years": {}},
    "gender_restriction": None,
    "states": [],
}


def blank(item, pdf_path):
    slug = f"{item['board'].lower()}-{Path(pdf_path).stem}"
    return slug, {
        "slug": slug,
        "board": item["board"],
        "title": "",
        "advt_no": None,
        "source_url": item["source_url"],
        "pdf_url": item["pdf_url"],
        "published_on": None,
        "apply_start": None,
        "apply_end": None,
        "fee_by_category": {},
        "posts": [dict(POST)],
        "total_vacancies": None,
        "confidence": {},
        "needs_review": False,
        "review_reasons": [],
        "extracted_at": None,
        "is_sample": False,
        "_local_pdf": str(Path(pdf_path).relative_to(ROOT)),
        "_skip_reason": None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50)
    args = ap.parse_args()

    by_board = defaultdict(list)
    for it in discover(make_session()):
        by_board[it["board"]].append(it)
    mixed = [it for group in zip_longest(*by_board.values()) for it in group if it]

    TODO.mkdir(parents=True, exist_ok=True)
    have = {p.stem for p in TODO.glob("*.json")} | {p.stem for p in TODO.parent.glob("*.json")}
    # download_new skips PDFs already on disk, so pick those up first.
    got = []
    for it in mixed:
        p = pdf_path_for(it["pdf_url"])
        if p.exists() and len(got) < args.n:
            got.append({**it, "path": str(p)})
    if len(got) < args.n:
        got += download_new(make_session(), mixed, limit=args.n - len(got))
    written = 0
    for item in got:
        slug, doc = blank(item, item["path"])
        if slug in have:
            continue
        (TODO / f"{slug}.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False))
        written += 1
    print(f"{written} new todo files in {TODO.relative_to(ROOT)} (boards: {dict((b, len(v)) for b, v in by_board.items())})")


if __name__ == "__main__":
    main()
