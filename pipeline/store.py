"""Flat JSON store. One file, committed to git by the refresh workflow, so the
site is reproducible and the dataset itself is a portfolio artefact."""
import json
from pathlib import Path
from typing import Dict, List

from engine.schema import Notification

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "notifications.json"


def load() -> List[Notification]:
    if DATA_FILE.exists():
        raw = json.loads(DATA_FILE.read_text())
    else:
        try:  # Cloudflare Worker: cf/build.sh bakes the file into a module
            from pipeline._bundled import NOTIFICATIONS_JSON
        except ImportError:
            return []
        raw = json.loads(NOTIFICATIONS_JSON)
    return [Notification(**r) for r in raw]


def save(items: List[Notification]) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    by_slug: Dict[str, Notification] = {}
    for n in items:
        by_slug[n.slug] = n  # later wins, so re-extractions replace older ones
    rows = [json.loads(n.model_dump_json()) for n in by_slug.values()]
    rows.sort(key=lambda r: (r.get("apply_end") or "9999", r["slug"]))
    DATA_FILE.write_text(json.dumps(rows, indent=2, ensure_ascii=False))


def upsert(new: List[Notification]) -> int:
    existing = load()
    save(existing + new)
    return len(new)
