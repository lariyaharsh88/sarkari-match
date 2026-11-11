"""Cheap pre-filter so Gemini calls are spent only on actual recruitment notifications.

Government boards publish biodata formats, undertakings, CTC forms, syllabi, answer keys,
admit-card notices and Hindi duplicates next to the real advertisement. Each one would
cost a free-tier call and then be rejected by the gate anyway.
"""
import re
from typing import Optional, Tuple

SKIP_URL_WORDS = [
    "biodata", "bio-data", "bio_data", "undertaking", "ctc", "negotiation", "format", "form_", "_form", "+form",
    "syllabus", "answer", "result", "admit", "hall", "scorecard", "score-card", "interview-schedule", "schedule",
    "hindi", "marathi", "tamil", "telugu", "gujarati", "kannada", "bengali", "odia",
    "corrigendum", "addendum", "notice-", "important-notice", "faq", "instructions", "declaration",
]
NOTIFICATION_HINTS = re.compile(
    r"(vacanc|post|recruitment|advertisement|advt|eligibility|age limit|last date|online application|apply online|"
    r"educational qualification|application fee|pay scale|pay level)",
    re.I,
)
FORM_HINTS = re.compile(r"(signature of (the )?candidate|name of (the )?candidate|affix photo|undertaking|self[- ]declaration)", re.I)
DEVANAGARI = re.compile(r"[ऀ-ॿ]")


SCANNED = "too little text, probably a form or a scanned PDF"


def triage(pdf_url: str, text: str) -> Tuple[bool, Optional[str]]:
    """Return (should_extract, reason_if_not)."""
    u = pdf_url.lower().replace("%20", " ").replace("+", " ")
    for w in SKIP_URL_WORDS:
        if w.replace("+", " ") in u:
            return False, f"url suggests non-notification document ({w})"
    if len(text) < 3000:
        return False, SCANNED
    sample = text[:20000]
    dev = len(DEVANAGARI.findall(sample))
    if dev > 0.25 * len(sample):
        return False, "mostly Hindi text; the English version is extracted instead"
    hints = len(NOTIFICATION_HINTS.findall(sample))
    forms = len(FORM_HINTS.findall(sample))
    if hints < 4:
        return False, f"only {hints} recruitment keywords in the first pages"
    if forms > hints:
        return False, "reads like an application form, not a notification"
    return True, None
