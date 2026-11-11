"""Server-rendered site: matcher + one page per notification, board and qualification.

Run:  .venv/bin/uvicorn web.app:app --reload --port 8010
Deploy: any free Python host (Render, Fly, Vercel python runtime). Data is read from
data/notifications.json at startup; the daily workflow commits a fresh file.
"""
import json
import os
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, Form, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from engine.eligibility import match_all
from engine.schema import CATEGORIES, QUALIFICATION_LEVELS, CandidateProfile, Notification
from pipeline import store
from web import alerts

ROOT = Path(__file__).resolve().parent
SITE_URL = os.environ.get("SITE_URL", "http://localhost:8010")
SITE_NAME = os.environ.get("SITE_NAME", "Sarkari Match")
ALERTS_CRON_SECRET = os.environ.get("ALERTS_CRON_SECRET", "")

app = FastAPI(title=SITE_NAME)
# On Cloudflare the static/ folder is served by the ASSETS binding before requests reach the app.
app.mount("/static", StaticFiles(directory=str(ROOT / "static"), check_dir=False), name="static")
templates = Jinja2Templates(directory=str(ROOT / "templates"))

QUAL_LABELS = {"8th": "8th pass", "10th": "10th pass", "12th": "12th pass", "iti": "ITI", "diploma": "Diploma",
               "graduate": "Graduate", "postgraduate": "Post graduate", "phd": "PhD"}
STREAMS = ["arts", "science", "commerce", "engineering", "law", "medicine", "nursing", "pharmacy", "agriculture",
           "computer_science", "statistics", "mathematics", "economics", "education"]


class Data:
    items: List[Notification] = []
    loaded: Optional[date] = None

    @classmethod
    def refresh(cls):
        cls.items = [n for n in store.load() if not n.needs_review]
        cls.loaded = date.today()

    @classmethod
    def by_slug(cls, slug: str) -> Optional[Notification]:
        return next((n for n in cls.items if n.slug == slug), None)

    @classmethod
    def open_items(cls, today: Optional[date] = None) -> List[Notification]:
        today = today or date.today()
        return [n for n in cls.items if n.apply_end is None or n.apply_end >= today]


Data.refresh()


def ctx(request: Request, **kw) -> Dict:
    base = {"request": request, "site": SITE_NAME, "site_url": SITE_URL, "today": date.today(),
            "qual_labels": QUAL_LABELS, "has_samples": any(n.is_sample for n in Data.items)}
    base.update(kw)
    return base


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    open_now = sorted(Data.open_items(), key=lambda n: n.apply_end or date.max)
    boards = sorted({n.board for n in Data.items})
    return templates.TemplateResponse(request, "index.html", ctx(request, open_items=open_now, boards=boards,
                                                        quals=list(QUALIFICATION_LEVELS), categories=CATEGORIES,
                                                        streams=STREAMS, matches=None, profile=None))


@app.post("/match", response_class=HTMLResponse)
async def match(request: Request, age: int = Form(...), qualification: str = Form(...), category: str = Form("UR"),
          gender: str = Form(""), state: str = Form(""), streams: List[str] = Form([]),
          pwd: bool = Form(False), ex_serviceman: bool = Form(False)):
    profile = CandidateProfile(age=age, qualification=qualification, category=category, gender=gender or None,
                               state=state or None, streams=streams, pwd=pwd, ex_serviceman=ex_serviceman)
    matches = match_all(Data.open_items(), profile)
    open_now = sorted(Data.open_items(), key=lambda n: n.apply_end or date.max)
    boards = sorted({n.board for n in Data.items})
    return templates.TemplateResponse(request, "index.html", ctx(request, open_items=open_now, boards=boards,
                                                        quals=list(QUALIFICATION_LEVELS), categories=CATEGORIES,
                                                        streams=STREAMS, matches=matches, profile=profile))


@app.get("/jobs/{slug}", response_class=HTMLResponse)
async def job(request: Request, slug: str):
    n = Data.by_slug(slug)
    if n is None:
        return HTMLResponse("Not found", status_code=404)
    jsonld = [{
        "@context": "https://schema.org", "@type": "JobPosting", "title": p.post_name,
        "description": p.qualification_text or n.title, "datePosted": (n.published_on or date.today()).isoformat(),
        "validThrough": n.apply_end.isoformat() if n.apply_end else None,
        "hiringOrganization": {"@type": "Organization", "name": n.board},
        "jobLocation": {"@type": "Place", "address": {"@type": "PostalAddress", "addressCountry": "IN"}},
        "employmentType": "FULL_TIME", "url": f"{SITE_URL}/jobs/{n.slug}",
    } for p in n.posts]
    return templates.TemplateResponse(request, "job.html", ctx(request, n=n, jsonld=json.dumps(jsonld)))


@app.get("/board/{board}", response_class=HTMLResponse)
async def board(request: Request, board: str):
    items = sorted([n for n in Data.items if n.board.lower() == board.lower()], key=lambda n: n.apply_end or date.max)
    if not items:
        return HTMLResponse("Not found", status_code=404)
    return templates.TemplateResponse(request, "list.html", ctx(request, heading=f"{items[0].board} recruitment notifications",
                                                       intro=f"Every open {items[0].board} notification with vacancies, eligibility and the last date to apply.",
                                                       items=items))


@app.get("/qualification/{qual}", response_class=HTMLResponse)
async def qualification(request: Request, qual: str):
    if qual not in QUALIFICATION_LEVELS:
        return HTMLResponse("Not found", status_code=404)
    have = QUALIFICATION_LEVELS[qual]
    items = [n for n in Data.open_items() if any(QUALIFICATION_LEVELS.get(p.min_qualification, 99) <= have for p in n.posts)]
    items.sort(key=lambda n: n.apply_end or date.max)
    label = QUAL_LABELS[qual]
    return templates.TemplateResponse(request, "list.html", ctx(request, heading=f"Government jobs for {label} candidates",
                                                       intro=f"Open notifications where at least one post accepts {label} as the minimum qualification.",
                                                       items=items))


@app.get("/admin/review", response_class=HTMLResponse)
async def review(request: Request):
    pending = [n for n in store.load() if n.needs_review]
    return templates.TemplateResponse(request, "review.html", ctx(request, items=pending))


# ---- paid alerts -------------------------------------------------------------

def _profile_from_form(age: int, qualification: str, category: str, gender: str, state: str, streams: List[str],
                       pwd: bool, ex_serviceman: bool) -> CandidateProfile:
    return CandidateProfile(age=age, qualification=qualification, category=category, gender=gender or None,
                            state=state or None, streams=streams, pwd=pwd, ex_serviceman=ex_serviceman)


@app.get("/alerts", response_class=HTMLResponse)
async def alerts_page(request: Request):
    q = request.query_params
    prefill = {"email": q.get("email"), "age": q.get("age"), "qualification": q.get("qualification"), "category": q.get("category"),
               "gender": q.get("gender"), "state": q.get("state"), "streams": q.getlist("streams"),
               "pwd": q.get("pwd") == "true", "ex_serviceman": q.get("ex_serviceman") == "true"}
    return templates.TemplateResponse(request, "alerts.html", ctx(request, quals=list(QUALIFICATION_LEVELS), categories=CATEGORIES, streams=STREAMS,
                                                         prefill=prefill, price=alerts.ALERT_PRICE_INR, days=alerts.ALERT_PASS_DAYS,
                                                         demo=not alerts.payments_enabled()))


@app.post("/api/alerts/order")
async def alerts_order(email: str = Form(...), age: int = Form(...), qualification: str = Form(...), category: str = Form("UR"),
                 gender: str = Form(""), state: str = Form(""), streams: List[str] = Form([]),
                 pwd: bool = Form(False), ex_serviceman: bool = Form(False)):
    """Saves the profile, then either creates a Razorpay order or (no keys) activates a free demo pass."""
    if qualification not in QUALIFICATION_LEVELS or category not in CATEGORIES:
        return JSONResponse({"error": "Invalid profile"}, status_code=400)
    sub = alerts.create(email, _profile_from_form(age, qualification, category, gender, state, streams, pwd, ex_serviceman))
    manage_url = f"/alerts/manage/{alerts.manage_token(sub.id)}"
    if not alerts.payments_enabled():
        alerts.activate(sub, "demo")
        return {"mode": "demo", "sub_id": sub.id, "manage_url": manage_url}
    try:
        order = await alerts.create_order(receipt=f"alerts_{sub.id}")
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=502)
    sub.order_id = order["id"]
    alerts.put(sub)
    return {"mode": "razorpay", "sub_id": sub.id, "key_id": alerts.RAZORPAY_KEY_ID, "order_id": order["id"],
            "amount": order["amount"], "currency": order["currency"], "manage_url": manage_url}


@app.post("/api/alerts/verify")
async def alerts_verify(request: Request):
    body = await request.json()
    sub = alerts.get(str(body.get("sub_id", "")))
    order_id, payment_id, sig = (str(body.get(k, "")) for k in ("razorpay_order_id", "razorpay_payment_id", "razorpay_signature"))
    if sub is None or sub.order_id != order_id:
        return JSONResponse({"error": "Unknown order"}, status_code=400)
    if not alerts.verify_signature(order_id, payment_id, sig):
        return JSONResponse({"error": "Signature mismatch"}, status_code=400)
    alerts.activate(sub, payment_id)
    return {"manage_url": f"/alerts/manage/{alerts.manage_token(sub.id)}"}


@app.get("/alerts/manage", response_class=HTMLResponse)
async def alerts_manage_help(request: Request):
    return templates.TemplateResponse(request, "alerts_manage.html", ctx(request, sub=None))


@app.get("/alerts/manage/{token}", response_class=HTMLResponse)
async def alerts_manage(request: Request, token: str):
    sub_id = alerts.parse_manage_token(token)
    sub = alerts.get(sub_id) if sub_id else None
    if sub is None:
        return HTMLResponse("Not found", status_code=404)
    matches = [m for m in match_all(Data.open_items(), sub.profile) if m.eligible]
    return templates.TemplateResponse(request, "alerts_manage.html", ctx(request, sub=sub, token=token, matches=matches))


@app.post("/alerts/manage/{token}/{action}")
async def alerts_toggle(token: str, action: str):
    sub_id = alerts.parse_manage_token(token)
    sub = alerts.get(sub_id) if sub_id else None
    if sub is None or action not in ("stop", "resume"):
        return HTMLResponse("Not found", status_code=404)
    sub.unsubscribed = action == "stop"
    alerts.put(sub)
    return RedirectResponse(f"/alerts/manage/{token}", status_code=303)


@app.post("/api/alerts/dispatch")
async def alerts_dispatch(authorization: Optional[str] = Header(None)):
    """Cron hook: email subscribers about new matches. Bearer ALERTS_CRON_SECRET required."""
    if not ALERTS_CRON_SECRET or authorization != f"Bearer {ALERTS_CRON_SECRET}":
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    Data.refresh()
    return await alerts.dispatch(Data.items)


@app.get("/sitemap.xml")
async def sitemap():
    urls = [f"{SITE_URL}/"] + [f"{SITE_URL}/jobs/{n.slug}" for n in Data.items]
    urls += [f"{SITE_URL}/board/{b}" for b in sorted({n.board for n in Data.items})]
    urls += [f"{SITE_URL}/qualification/{q}" for q in QUALIFICATION_LEVELS] + [f"{SITE_URL}/alerts"]
    body = "".join(f"<url><loc>{u}</loc></url>" for u in urls)
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>',
                    media_type="application/xml")


@app.get("/robots.txt")
async def robots():
    return PlainTextResponse(f"User-agent: *\nAllow: /\nDisallow: /admin/\nDisallow: /alerts/manage/\nSitemap: {SITE_URL}/sitemap.xml\n")


@app.get("/api/stats")
async def stats():
    """Numbers for the case study. Snapshot these weekly with scripts/metrics_snapshot.py."""
    by_board = defaultdict(int)
    for n in Data.items:
        by_board[n.board] += 1
    return {"notifications": len(Data.items), "open": len(Data.open_items()),
            "posts": sum(len(n.posts) for n in Data.items),
            "vacancies": sum(n.total_vacancies or 0 for n in Data.items),
            "boards": dict(by_board), "samples": sum(1 for n in Data.items if n.is_sample)}
