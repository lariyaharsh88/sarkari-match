from datetime import date, timedelta

import pytest

from engine.schema import AgeRule, CandidateProfile, Notification, Post
from web import alerts


@pytest.fixture(autouse=True)
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(alerts, "SUBSCRIBERS_FILE", tmp_path / "subs.json")
    monkeypatch.setattr(alerts, "RESEND_API_KEY", "")


def notif(slug: str, min_q: str = "graduate", max_age: int = 30) -> Notification:
    return Notification(slug=slug, board="SSC", title=f"{slug} title", source_url="https://ssc.gov.in", apply_end=date.today() + timedelta(days=10),
                        posts=[Post(post_name="Clerk", min_qualification=min_q, age=AgeRule(min_age=18, max_age=max_age))])


def test_create_activate_and_tokens():
    sub = alerts.create("A@Example.com", CandidateProfile(age=25, qualification="graduate"))
    assert sub.email == "a@example.com" and not sub.active
    alerts.activate(sub, "pay_1")
    assert alerts.get(sub.id).active
    assert alerts.get(sub.id).paid_until == date.today() + timedelta(days=alerts.ALERT_PASS_DAYS)
    tok = alerts.manage_token(sub.id)
    assert alerts.parse_manage_token(tok) == sub.id
    assert alerts.parse_manage_token(tok[:-2] + "zz") is None
    assert alerts.parse_manage_token("garbage") is None


def test_dispatch_only_new_eligible_and_marks_sent():
    sub = alerts.activate(alerts.create("a@example.com", CandidateProfile(age=25, qualification="graduate")))
    items = [notif("ssc-cgl"), notif("ssc-mts", min_q="10th"), notif("old-age", max_age=20)]
    r = alerts.dispatch(items)
    assert r == {"sent": 1, "skipped": 0, "failed": 0, "subscribers": 1}
    assert alerts.get(sub.id).notified_slugs == ["ssc-cgl", "ssc-mts"]
    # second run: nothing new
    assert alerts.dispatch(items)["sent"] == 0
    # a new notification arrives
    assert alerts.dispatch(items + [notif("ssc-chsl")])["sent"] == 1
    assert "ssc-chsl" in alerts.get(sub.id).notified_slugs


def test_inactive_or_stopped_subscribers_skipped():
    alerts.create("unpaid@example.com", CandidateProfile(age=25, qualification="graduate"))
    stopped = alerts.activate(alerts.create("stopped@example.com", CandidateProfile(age=25, qualification="graduate")))
    stopped.unsubscribed = True
    alerts.put(stopped)
    assert alerts.dispatch([notif("ssc-cgl")]) == {"sent": 0, "skipped": 2, "failed": 0, "subscribers": 2}


def test_razorpay_signature(monkeypatch):
    monkeypatch.setattr(alerts, "RAZORPAY_KEY_SECRET", "secret")
    import hashlib, hmac
    sig = hmac.new(b"secret", b"order_1|pay_1", hashlib.sha256).hexdigest()
    assert alerts.verify_signature("order_1", "pay_1", sig)
    assert not alerts.verify_signature("order_1", "pay_2", sig)
