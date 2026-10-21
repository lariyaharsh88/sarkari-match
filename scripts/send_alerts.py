"""Email active alert subscribers about new eligible notifications.

Run after scripts/refresh.py, on the same host that holds SUBSCRIBERS_FILE:
    .venv/bin/python scripts/send_alerts.py
The deployed app exposes the same job at POST /api/alerts/dispatch (bearer ALERTS_CRON_SECRET)
so a GitHub Actions cron can trigger it without access to the subscriber file.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from pipeline import store  # noqa: E402
from web import alerts  # noqa: E402

if __name__ == "__main__":
    print("[alerts]", alerts.dispatch(store.load()))
