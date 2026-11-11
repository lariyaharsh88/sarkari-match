"""Re-run the extractor on every PDF that has a gold label, writing evals/predictions/.
Expects evals/gold/<slug>.json to carry pdf_url (or a local PDF at data/pdfs/<slug>.pdf)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.extract import extract, pdf_text  # noqa: E402
from pipeline.fetch import download_new, make_session  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
session = make_session()
for gf in sorted((ROOT / "evals" / "gold").glob("*.json")):
    g = json.loads(gf.read_text())
    if g.get("is_sample"):
        print(f"skip sample {gf.name}")
        continue
    local = ROOT / (g.get("_local_pdf") or f"data/pdfs/{g['slug']}.pdf")
    if not local.exists() and g.get("pdf_url"):
        got = download_new(session, [{"board": g["board"], "pdf_url": g["pdf_url"], "source_url": g["source_url"]}], limit=1)
        if got:
            local = Path(got[0]["path"])
    if not local.exists():
        print(f"no PDF for {g['slug']}")
        continue
    n = extract(pdf_text(local), g["board"], g["source_url"], g.get("pdf_url"))
    (ROOT / "evals" / "predictions" / gf.name).write_text(n.model_dump_json(indent=2))
    print(f"predicted {g['slug']}")
