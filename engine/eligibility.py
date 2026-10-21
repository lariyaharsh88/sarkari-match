"""Rules engine: does a candidate qualify for a post?

Pure functions, no I/O. Every decision returns the rule that produced it so the
UI can show *why* someone is in or out. Keep this file boring and well tested;
it is the product's moat.
"""
from datetime import date
from typing import List, Optional

from .schema import (
    DEFAULT_AGE_RELAXATION,
    QUALIFICATION_LEVELS,
    AgeRule,
    CandidateProfile,
    MatchReason,
    Notification,
    Post,
    PostMatch,
)


def effective_max_age(rule: AgeRule, profile: CandidateProfile) -> Optional[int]:
    """Max age after category and status relaxations. None means no cap."""
    if rule.max_age is None:
        return None
    relax = dict(DEFAULT_AGE_RELAXATION)
    relax.update(rule.relaxation_years)
    extra = 0
    if profile.category in ("OBC", "SC", "ST"):
        extra = relax.get(profile.category, 0)
    # PwD and ex-serviceman relaxations are additive to the category relaxation
    # under central government rules.
    if profile.pwd:
        extra += relax.get("PWD", 0)
    if profile.ex_serviceman:
        extra += relax.get("EX_SERVICEMAN", 0)
    if profile.gender == "female" and "WOMEN" in relax:
        extra += relax["WOMEN"]
    return rule.max_age + extra


def check_age(post: Post, profile: CandidateProfile) -> MatchReason:
    rule = post.age
    cap = effective_max_age(rule, profile)
    if rule.min_age is not None and profile.age < rule.min_age:
        return MatchReason(rule="age", passed=False, detail=f"Minimum age is {rule.min_age}, you are {profile.age}")
    if cap is not None and profile.age > cap:
        base = f"Maximum age is {rule.max_age}"
        if cap != rule.max_age:
            base += f" ({cap} after relaxation for {profile.category}{', PwD' if profile.pwd else ''}{', ex-serviceman' if profile.ex_serviceman else ''})"
        return MatchReason(rule="age", passed=False, detail=f"{base}, you are {profile.age}")
    detail = "No age limit stated" if cap is None else f"Within age limit of {cap}"
    return MatchReason(rule="age", passed=True, detail=detail)


def check_qualification(post: Post, profile: CandidateProfile) -> MatchReason:
    need = QUALIFICATION_LEVELS.get(post.min_qualification)
    have = QUALIFICATION_LEVELS.get(profile.qualification)
    if need is None:
        return MatchReason(rule="qualification", passed=False, detail=f"Unknown requirement '{post.min_qualification}', needs review")
    if have is None:
        return MatchReason(rule="qualification", passed=False, detail=f"Unknown candidate qualification '{profile.qualification}'")
    if have < need:
        return MatchReason(rule="qualification", passed=False, detail=f"Requires {post.min_qualification}, you have {profile.qualification}")
    if post.required_streams:
        if not set(s.lower() for s in post.required_streams) & set(s.lower() for s in profile.streams):
            return MatchReason(
                rule="qualification",
                passed=False,
                detail=f"Requires a degree in {', '.join(post.required_streams)}",
            )
    return MatchReason(rule="qualification", passed=True, detail=f"Meets {post.min_qualification} requirement")


def check_gender(post: Post, profile: CandidateProfile) -> MatchReason:
    if post.gender_restriction and profile.gender and post.gender_restriction != profile.gender:
        return MatchReason(rule="gender", passed=False, detail=f"Post is open to {post.gender_restriction} candidates only")
    return MatchReason(rule="gender", passed=True, detail="No gender restriction applies")


def check_state(post: Post, profile: CandidateProfile) -> MatchReason:
    if post.states and profile.state and profile.state.lower() not in [s.lower() for s in post.states]:
        return MatchReason(rule="state", passed=False, detail=f"Domicile required: {', '.join(post.states)}")
    return MatchReason(rule="state", passed=True, detail="No domicile restriction applies")


def check_window(n: Notification, today: date) -> MatchReason:
    if n.apply_end and today > n.apply_end:
        return MatchReason(rule="deadline", passed=False, detail=f"Applications closed on {n.apply_end.isoformat()}")
    if n.apply_start and today < n.apply_start:
        return MatchReason(rule="deadline", passed=True, detail=f"Applications open from {n.apply_start.isoformat()}")
    if n.apply_end:
        days = (n.apply_end - today).days
        return MatchReason(rule="deadline", passed=True, detail=f"{days} days left to apply")
    return MatchReason(rule="deadline", passed=True, detail="Deadline not stated")


def match_post(n: Notification, post: Post, profile: CandidateProfile, today: Optional[date] = None) -> PostMatch:
    today = today or date.today()
    reasons = [
        check_window(n, today),
        check_qualification(post, profile),
        check_age(post, profile),
        check_gender(post, profile),
        check_state(post, profile),
    ]
    return PostMatch(
        notification_slug=n.slug,
        board=n.board,
        title=n.title,
        post_name=post.post_name,
        apply_end=n.apply_end,
        eligible=all(r.passed for r in reasons),
        reasons=reasons,
    )


def match_all(notifications: List[Notification], profile: CandidateProfile, today: Optional[date] = None) -> List[PostMatch]:
    out: List[PostMatch] = []
    for n in notifications:
        for post in n.posts:
            out.append(match_post(n, post, profile, today))
    # Eligible first, soonest deadline first.
    out.sort(key=lambda m: (not m.eligible, m.apply_end or date.max))
    return out
