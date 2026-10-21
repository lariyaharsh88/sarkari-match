"""Remembers what happened to every PDF so nothing is silently skipped or re-paid for."""
import json
from datetime import date
from pathlib import Path
from typing import Dict

LEDGER = Path(__file__).resolve().parent.parent / "data" / "ledger.json"


def load() -> Dict[str, Dict]:
    return json.loads(LEDGER.read_text()) if LEDGER.exists() else {}


def save(d: Dict[str, Dict]) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(d, indent=2, ensure_ascii=False))


def record(d: Dict[str, Dict], key: str, status: str, note: str = "", **extra) -> None:
    d[key] = {"status": status, "note": note, "date": date.today().isoformat(), **extra}
