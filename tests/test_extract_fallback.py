import json

import pytest

from pipeline import extract as ex

GOOD = json.dumps({"slug": "ssc-x", "board": "SSC", "title": "X", "source_url": "u",
                   "posts": [{"post_name": "Clerk", "min_qualification": "12th"}]})


def quota(*a, **k):
    raise RuntimeError("429 RESOURCE_EXHAUSTED")


def test_falls_back_to_groq_on_quota(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.setattr(ex, "_gemini_json", quota)
    seen = {}
    monkeypatch.setattr(ex, "_groq_json", lambda prompt, schema: seen.setdefault("p", prompt) and GOOD)
    n = ex.extract("x" * 50000, "SSC", "u")
    assert n.posts[0].post_name == "Clerk" and len(seen["p"]) < 50000


def test_no_fallback_without_key_or_for_scans(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr(ex, "_gemini_json", quota)
    with pytest.raises(RuntimeError, match="429"):
        ex.extract("text", "SSC", "u")
    monkeypatch.setenv("GROQ_API_KEY", "k")
    with pytest.raises(RuntimeError, match="429"):
        ex.extract("", "SSC", "u", pdf_bytes=b"%PDF")


def test_fallback_output_goes_to_review(monkeypatch):
    from pipeline.validate import apply_gate
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.setattr(ex, "_gemini_json", quota)
    monkeypatch.setattr(ex, "_groq_json", lambda p, s: GOOD)
    n = ex.extract("text", "SSC", "u")
    assert n.needs_review
    try:
        n = apply_gate(n)
    except ValueError:
        return  # hard-rejected is fine too; it never reaches the site either way
    assert n.needs_review and any("fallback" in r for r in n.review_reasons)
