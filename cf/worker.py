"""Cloudflare Python Worker entry: runs the FastAPI app from web/app.py.

Secrets and vars arrive on self.env, not os.environ, so they are copied across
before the app module (which reads os.environ at import) is first imported.
Alert subscribers live in KV under one key; see web/alerts.py (_memory).
"""
import json
import os

from workers import WorkerEntrypoint, asgi

ENV_KEYS = ["SITE_URL", "SITE_NAME", "RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET", "ALERTS_TOKEN_SECRET",
            "ALERTS_CRON_SECRET", "RESEND_API_KEY", "ALERT_FROM", "ALERT_PRICE_INR", "ALERT_PASS_DAYS"]
SUBS_KEY = "subscribers.json"
_app = None


def get_app(env):
    global _app
    if _app is None:
        for k in ENV_KEYS:
            v = getattr(env, k, None)
            if isinstance(v, str) and v:
                os.environ[k] = v
        from web.app import app
        _app = app
    return _app


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        app = get_app(self.env)
        from web import alerts
        raw = await self.env.SUBSCRIBERS.get(SUBS_KEY)
        alerts._memory = json.loads(raw) if raw else []
        alerts._dirty = False
        response = await asgi.fetch(app, request, self.env, self.ctx)
        if alerts._dirty:
            await self.env.SUBSCRIBERS.put(SUBS_KEY, json.dumps(alerts._memory))
        return response
