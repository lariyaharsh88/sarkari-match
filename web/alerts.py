"""Paid eligibility alerts: subscriber store, Razorpay helpers, dispatch.

No database. Subscribers live in one JSON file (SUBSCRIBERS_FILE, default
data/subscribers.json, gitignored because it holds emails). Payment is a one-time
pass for ALERT_PASS_DAYS days, verified by Razorpay's HMAC signature. Without
Razorpay keys the pass activates for free (demo mode) so the flow can be tested.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import httpx
from pydantic import BaseModel, Field

from engine.eligibility import match_all
from engine.schema import CandidateProfile, Notification, PostMatch

SUBSCRIBERS_FILE = Path(os.environ.get("SUBSCRIBERS_FILE") or Path(__file__).resolve().parent.parent / "data" / "subscribers.json")
ALERT_PRICE_INR = int(os.environ.get("ALERT_PRICE_INR", "99"))
ALERT_PASS_DAYS = int(os.environ.get("ALERT_PASS_DAYS", "180"))
RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")
TOKEN_SECRET = os.environ.get("ALERTS_TOKEN_SECRET") or RAZORPAY_KEY_SECRET or "dev-alerts-secret-change-me"
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
ALERT_FROM = os.environ.get("ALERT_FROM", "alerts@example.com")
SITE_URL = os.environ.get("SITE_URL", "http://localhost:8010")
SITE_NAME = os.environ.get("SITE_NAME", "Sarkari Match")


def payments_enabled() -> bool:
    return bool(RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET)


class Subscriber(BaseModel):
    id: str
    email: str
    profile: CandidateProfile
    created_at: datetime
    paid_until: Optional[date] = None
    order_id: Optional[str] = None
    payment_id: Optional[str] = None
    notified_slugs: List[str] = Field(default_factory=list)
    unsubscribed: bool = False

    @property
    def active(self) -> bool:
        return not self.unsubscribed and self.paid_until is not None and self.paid_until >= date.today()


# ---- store ----------------------------------------------------------------
# Locally: the JSON file. On Cloudflare Workers there is no writable disk, so
# cf/worker.py loads the rows from KV into _memory before each request and
# writes them back afterwards if _dirty.
_memory: Optional[List[Dict]] = None
_dirty = False


def load() -> List[Subscriber]:
    if _memory is not None:
        return [Subscriber(**r) for r in _memory]
    if not SUBSCRIBERS_FILE.exists():
        return []
    return [Subscriber(**r) for r in json.loads(SUBSCRIBERS_FILE.read_text())]


def save(subs: List[Subscriber]) -> None:
    global _memory, _dirty
    if _memory is not None:
        _memory = [json.loads(s.model_dump_json()) for s in subs]
        _dirty = True
        return
    SUBSCRIBERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SUBSCRIBERS_FILE.write_text(json.dumps([json.loads(s.model_dump_json()) for s in subs], indent=2, ensure_ascii=False))


def get(sub_id: str) -> Optional[Subscriber]:
    return next((s for s in load() if s.id == sub_id), None)


def put(sub: Subscriber) -> None:
    subs = [s for s in load() if s.id != sub.id]
    subs.append(sub)
    save(subs)


def create(email: str, profile: CandidateProfile) -> Subscriber:
    sub = Subscriber(id=secrets.token_urlsafe(12), email=email.strip().lower(), profile=profile, created_at=datetime.utcnow())
    put(sub)
    return sub


def activate(sub: Subscriber, payment_id: Optional[str] = None) -> Subscriber:
    base = sub.paid_until if sub.paid_until and sub.paid_until >= date.today() else date.today()
    sub.paid_until = base + timedelta(days=ALERT_PASS_DAYS)
    sub.payment_id = payment_id
    sub.unsubscribed = False
    put(sub)
    return sub


# ---- razorpay ---------------------------------------------------------------

async def create_order(receipt: str) -> Dict:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post("https://api.razorpay.com/v1/orders", auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET),
                              json={"amount": ALERT_PRICE_INR * 100, "currency": "INR", "receipt": receipt, "notes": {"product": "alerts"}})
    if r.status_code >= 300:
        raise RuntimeError(f"Razorpay order failed ({r.status_code}): {r.text[:300]}")
    return r.json()


def verify_signature(order_id: str, payment_id: str, signature: str) -> bool:
    expected = hmac.new(RAZORPAY_KEY_SECRET.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


# ---- manage tokens (link in every email) --------------------------------------

def manage_token(sub_id: str) -> str:
    sig = hmac.new(TOKEN_SECRET.encode(), sub_id.encode(), hashlib.sha256).digest()[:16]
    return f"{sub_id}.{base64.urlsafe_b64encode(sig).decode().rstrip('=')}"


def parse_manage_token(token: str) -> Optional[str]:
    sub_id, _, sig = token.partition(".")
    if not sub_id or not sig:
        return None
    return sub_id if hmac.compare_digest(manage_token(sub_id), token) else None


# ---- dispatch -----------------------------------------------------------------

def new_matches(sub: Subscriber, notifications: List[Notification], today: Optional[date] = None) -> List[PostMatch]:
    """Eligible posts from notifications this subscriber has not been told about yet."""
    seen = set(sub.notified_slugs)
    return [m for m in match_all(notifications, sub.profile, today) if m.eligible and m.notification_slug not in seen]


def render_email(sub: Subscriber, matches: List[PostMatch]) -> str:
    by_slug: Dict[str, List[PostMatch]] = {}
    for m in matches:
        by_slug.setdefault(m.notification_slug, []).append(m)
    rows = []
    for slug, ms in by_slug.items():
        posts = ", ".join(m.post_name for m in ms)
        end = f" · apply by {ms[0].apply_end}" if ms[0].apply_end else ""
        rows.append(f'<li><a href="{SITE_URL}/jobs/{slug}">{ms[0].title}</a> ({ms[0].board}){end}<br><small>Eligible for: {posts}</small></li>')
    return (f"<p>{len(by_slug)} new government job notification{'s' if len(by_slug) != 1 else ''} you are eligible for, "
            f"based on your profile (age {sub.profile.age}, {sub.profile.qualification}, {sub.profile.category}):</p>"
            f"<ul>{''.join(rows)}</ul>"
            f"<p><small>Always confirm on the official notification before applying. "
            f'<a href="{SITE_URL}/alerts/manage/{manage_token(sub.id)}">Manage or stop alerts</a>.</small></p>')


async def send_email(to: str, subject: str, html: str) -> bool:
    """Resend REST API. Without a key, prints the email and reports success so local runs work."""
    if not RESEND_API_KEY:
        print(f"[alerts] (no RESEND_API_KEY) would email {to}: {subject}")
        return True
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post("https://api.resend.com/emails", headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
                              json={"from": f"{SITE_NAME} <{ALERT_FROM}>", "to": [to], "subject": subject, "html": html})
    if r.status_code >= 300:
        print(f"[alerts] email to {to} failed ({r.status_code}): {r.text[:200]}")
        return False
    return True


async def dispatch(notifications: List[Notification], today: Optional[date] = None) -> Dict[str, int]:
    """Email every active subscriber about newly matching open notifications."""
    today = today or date.today()
    open_items = [n for n in notifications if not n.needs_review and (n.apply_end is None or n.apply_end >= today)]
    sent = skipped = failed = 0
    subs = load()
    for sub in subs:
        if not sub.active:
            skipped += 1
            continue
        matches = new_matches(sub, open_items, today)
        if not matches:
            skipped += 1
            continue
        n_notifs = len({m.notification_slug for m in matches})
        ok = await send_email(sub.email, f"{n_notifs} new government job{'s' if n_notifs != 1 else ''} you can apply for", render_email(sub, matches))
        if ok:
            sub.notified_slugs = sorted(set(sub.notified_slugs) | {m.notification_slug for m in matches})
            sent += 1
        else:
            failed += 1
    save(subs)
    return {"sent": sent, "skipped": skipped, "failed": failed, "subscribers": len(subs)}
