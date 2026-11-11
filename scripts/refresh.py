"""End-to-end refresh: discover -> download new -> triage -> extract -> validate -> store.

Run locally:  .venv/bin/python scripts/refresh.py --limit 10
In CI this runs daily and commits data/notifications.json plus data/ledger.json.

Every PDF on disk that the ledger has not marked stored/rejected/skipped is processed, so
a run that fails half way (no key, quota hit) simply resumes next time.
"""
import argparse
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

from pipeline import fetch, ledger, store  # noqa: E402
from pipeline.extract import extract, pdf_text  # noqa: E402
from pipeline.triage import SCANNED, triage  # noqa: E402
from pipeline.validate import apply_gate  # noqa: E402

logging.getLogger("pdfminer").setLevel(logging.ERROR)  # silences the "invalid float value" colour warnings
load_dotenv()


def main(limit: int, dry_run: bool) -> int:
    if not dry_run and not os.environ.get("GEMINI_API_KEY"):
        print("GEMINI_API_KEY is not set. Create a free key at https://aistudio.google.com/apikey, put it in .env, and rerun.")
        print("Use --dry-run to discover and download without extracting.")
        return 2

    session = fetch.make_session()
    found = fetch.discover(session)
    print(f"[refresh] discovered {len(found)} candidate PDFs across boards")
    url_by_path = {str(fetch.pdf_path_for(i["pdf_url"])): i for i in found}
    new = fetch.download_new(session, fetch.interleave(found), limit=limit)
    print(f"[refresh] downloaded {len(new)} new PDFs")
    if dry_run:
        return 0

    book = ledger.load()
    pending = []
    for path in sorted(fetch.PDF_DIR.glob("*.pdf")):
        key = path.stem
        if book.get(key, {}).get("status") in ("stored", "rejected", "skipped"):
            continue
        meta = url_by_path.get(str(path)) or book.get(key, {}).get("meta")
        if not meta:
            ledger.record(book, key, "skipped", "no source metadata for this file")
            continue
        pending.append((key, path, meta))
    print(f"[refresh] {len(pending)} PDFs awaiting extraction")

    accepted, calls = [], 0
    for key, path, meta in pending:
        if calls >= limit:
            print(f"[refresh] reached --limit {limit} Gemini calls, the rest resume next run")
            break
        try:
            text = pdf_text(path)
            ok, why = triage(meta["pdf_url"], text)
            scanned = why == SCANNED and path.stat().st_size > 150_000  # big image-only PDF, not a one-page form
            if not ok and not scanned:
                ledger.record(book, key, "skipped", why, meta=meta)
                print(f"[triage] skip {path.name}: {why}")
                continue
            calls += 1
            n = extract(text, meta["board"], meta["source_url"], meta["pdf_url"],
                        pdf_bytes=path.read_bytes() if scanned else None)
            if scanned and not n.posts:
                ledger.record(book, key, "skipped", "scanned PDF, not a recruitment notification", meta=meta)
                print(f"[triage] skip {path.name}: scanned, no posts")
                continue
            n = apply_gate(n)
            accepted.append(n)
            ledger.record(book, key, "stored", n.slug, meta=meta, needs_review=n.needs_review)
            print(f"[extract] ok {n.slug} posts={len(n.posts)} review={n.needs_review}")
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            if "quota" in msg.lower() or "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                print(f"[extract] Gemini quota hit, stopping; {path.name} will be retried next run")
                break
            if "validation" not in msg.lower():  # API/config errors are ours, not the PDF's: retry next run
                print(f"[extract] error on {path.name}, will retry next run: {msg[:200]}")
                continue
            ledger.record(book, key, "rejected", msg[:300], meta=meta)
            print(f"[extract] rejected {path.name}: {msg[:200]}")
    store.upsert(accepted)
    ledger.save(book)
    counts = {}
    for v in book.values():
        counts[v["status"]] = counts.get(v["status"], 0) + 1
    print(f"[refresh] stored {len(accepted)} this run; ledger {counts}; site records {len(store.load())}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10, help="max new downloads and max Gemini calls per run")
    ap.add_argument("--dry-run", action="store_true", help="discover and download only")
    a = ap.parse_args()
    sys.exit(main(a.limit, a.dry_run))
