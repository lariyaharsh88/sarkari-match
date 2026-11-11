"""Discover and download notification PDFs from official listing pages."""
import hashlib
import re
import time
from pathlib import Path
from typing import Dict, List
from urllib.parse import urljoin

import requests

from .sources import SOURCES, USER_AGENT

PDF_DIR = Path(__file__).resolve().parent.parent / "data" / "pdfs"
HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.I)


def discover(session: requests.Session) -> List[Dict[str, str]]:
    found: List[Dict[str, str]] = []
    seen = set()
    for src in SOURCES:
        try:
            r = session.get(src["url"], timeout=30)
            r.raise_for_status()
        except Exception as e:  # noqa: BLE001
            print(f"[discover] {src['board']} {src['url']} failed: {e}")
            continue
        for href in HREF_RE.findall(r.text):
            if src["must_contain"].lower() not in href.lower():
                continue
            full = urljoin(src["url"], href)
            if full in seen:
                continue
            seen.add(full)
            found.append({"board": src["board"], "pdf_url": full, "source_url": src["url"]})
        time.sleep(2)
    return found


def interleave(items: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Round-robin by board so one site with hundreds of links cannot take every download slot."""
    by_board: Dict[str, List[Dict[str, str]]] = {}
    for it in items:
        by_board.setdefault(it["board"], []).append(it)
    out: List[Dict[str, str]] = []
    queues = list(by_board.values())
    while any(queues):
        for q in queues:
            if q:
                out.append(q.pop(0))
    return out


def pdf_path_for(url: str) -> Path:
    digest = hashlib.sha1(url.encode()).hexdigest()[:16]
    return PDF_DIR / f"{digest}.pdf"


def download_new(session: requests.Session, items: List[Dict[str, str]], limit: int = 25) -> List[Dict[str, str]]:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    for item in items:
        path = pdf_path_for(item["pdf_url"])
        if path.exists():
            continue
        try:
            r = session.get(item["pdf_url"], timeout=60)
            r.raise_for_status()
            if not r.content.startswith(b"%PDF"):
                continue
            path.write_bytes(r.content)
            item["path"] = str(path)
            out.append(item)
            print(f"[download] {item['board']} {path.name} ({len(r.content)//1024} KB)")
        except Exception as e:  # noqa: BLE001
            print(f"[download] {item['pdf_url']} failed: {e}")
        if len(out) >= limit:
            break
        time.sleep(2)
    return out


CERTS_DIR = Path(__file__).resolve().parent / "certs"


def _ca_bundle() -> str:
    """certifi's roots plus intermediates that some boards (IBPS, BPSC) forget to send.
    Browsers fetch missing intermediates themselves; Python on Linux does not."""
    import certifi
    out = CERTS_DIR / ".bundle.pem"
    out.write_text(Path(certifi.where()).read_text() + (CERTS_DIR / "intermediates.pem").read_text())
    return str(out)


def make_session() -> requests.Session:
    s = requests.Session()
    s.verify = _ca_bundle()
    s.headers["User-Agent"] = USER_AGENT
    return s
