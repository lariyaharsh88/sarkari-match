"""Validation gate. Nothing reaches the site without passing through here.

Hard failures reject the record. Soft failures mark it needs_review so it is
shown only after a human confirms it in the admin page.
"""
from datetime import date, timedelta
from typing import List, Tuple

from engine.schema import QUALIFICATION_LEVELS, Notification

CONFIDENCE_FLOOR = 0.7


def validate(n: Notification, today: date = None) -> Tuple[bool, List[str], List[str]]:
    today = today or date.today()
    hard: List[str] = []
    soft: List[str] = []

    if not n.title or len(n.title) < 8:
        hard.append("title missing or too short")
    if not n.posts:
        hard.append("no posts extracted")
    if n.apply_end and n.apply_start and n.apply_end < n.apply_start:
        hard.append("apply_end before apply_start")
    if n.apply_end and n.apply_end < today - timedelta(days=365):
        hard.append("deadline more than a year in the past, probably a stale PDF")

    for p in n.posts:
        if p.min_qualification not in QUALIFICATION_LEVELS:
            hard.append(f"post '{p.post_name}': unknown qualification '{p.min_qualification}'")
        if p.age.min_age is not None and p.age.max_age is not None and p.age.min_age > p.age.max_age:
            hard.append(f"post '{p.post_name}': min_age > max_age")
        if p.age.max_age is not None and not (15 <= p.age.max_age <= 70):
            soft.append(f"post '{p.post_name}': implausible max_age {p.age.max_age}")
        if p.vacancies is not None and p.vacancies_by_category:
            s = sum(p.vacancies_by_category.values())
            if s and abs(s - p.vacancies) > max(2, 0.05 * p.vacancies):
                soft.append(f"post '{p.post_name}': category vacancies sum {s} != total {p.vacancies}")

    if n.apply_end is None:
        soft.append("apply_end missing")
    if n.total_vacancies is not None and n.posts:
        s = sum(p.vacancies or 0 for p in n.posts)
        if s and abs(s - n.total_vacancies) > max(2, 0.05 * n.total_vacancies):
            soft.append(f"post vacancies sum {s} != total_vacancies {n.total_vacancies}")
    for field, conf in n.confidence.items():
        if conf < CONFIDENCE_FLOOR:
            soft.append(f"low confidence on {field}: {conf:.2f}")

    return (not hard), hard, soft


def apply_gate(n: Notification, today: date = None) -> Notification:
    ok, hard, soft = validate(n, today)
    if not ok:
        raise ValueError("; ".join(hard))
    n.review_reasons = [r for r in n.review_reasons if "fallback" in r] + soft  # keep the extractor's own flag
    n.needs_review = bool(n.review_reasons)
    return n
