"""Cloudflare Python Worker entry: runs the FastAPI app from web/app.py.

Secrets and vars arrive on self.env, not os.environ, so they are copied across
before the app module (which reads os.environ at import) is first imported.
Alert subscribers live in KV, one key per subscriber (see web/alerts.py).
"""
import os

from workers import WorkerEntrypoint, asgi

ENV_KEYS = ["SITE_URL", "SITE_NAME", "RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET", "ALERTS_TOKEN_SECRET",
            "ALERTS_CRON_SECRET", "RESEND_API_KEY", "ALERT_FROM", "ALERT_PRICE_INR", "ALERT_PASS_DAYS",
            "ADMIN_PASSWORD", "CONTACT_EMAIL", "TURNSTILE_SITE_KEY", "TURNSTILE_SECRET"]
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
        alerts.KV = self.env.SUBSCRIBERS
        return await asgi.fetch(app, request, self.env, self.ctx)

    async def scheduled(self, *args):
        # Cron warm-up: importing the app here keeps an isolate ready, so visitors
        # rarely hit the multi-second Python cold start.
        get_app(self.env)
