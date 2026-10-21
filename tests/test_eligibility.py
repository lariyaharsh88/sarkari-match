from datetime import date

from engine.eligibility import effective_max_age, match_all, match_post
from engine.schema import AgeRule, CandidateProfile, Notification, Post

TODAY = date(2026, 10, 14)


def _notif(**kw):
    base = dict(
        slug="ssc-cgl-2026",
        board="SSC",
        title="Combined Graduate Level 2026",
        source_url="https://ssc.gov.in",
        apply_start=date(2026, 9, 1),
        apply_end=date(2026, 10, 30),
        posts=[
            Post(
                post_name="Auditor",
                min_qualification="graduate",
                age=AgeRule(min_age=18, max_age=27, as_on=date(2026, 8, 1)),
            )
        ],
    )
    base.update(kw)
    return Notification(**base)


def test_graduate_within_age_is_eligible():
    m = match_post(_notif(), _notif().posts[0], CandidateProfile(age=24, qualification="graduate"), TODAY)
    assert m.eligible
    assert [r.rule for r in m.reasons] == ["deadline", "qualification", "age", "gender", "state"]


def test_12th_pass_fails_graduate_requirement():
    m = match_post(_notif(), _notif().posts[0], CandidateProfile(age=24, qualification="12th"), TODAY)
    assert not m.eligible
    bad = [r for r in m.reasons if not r.passed]
    assert bad[0].rule == "qualification"


def test_postgraduate_satisfies_graduate_requirement():
    m = match_post(_notif(), _notif().posts[0], CandidateProfile(age=24, qualification="postgraduate"), TODAY)
    assert m.eligible


def test_obc_gets_three_years_relaxation_by_default():
    rule = AgeRule(max_age=27)
    assert effective_max_age(rule, CandidateProfile(age=0, qualification="graduate", category="OBC")) == 30
    assert effective_max_age(rule, CandidateProfile(age=0, qualification="graduate", category="SC")) == 32
    assert effective_max_age(rule, CandidateProfile(age=0, qualification="graduate", category="UR")) == 27


def test_notification_relaxation_overrides_default():
    rule = AgeRule(max_age=30, relaxation_years={"OBC": 5})
    assert effective_max_age(rule, CandidateProfile(age=0, qualification="graduate", category="OBC")) == 35


def test_pwd_relaxation_is_additive_to_category():
    rule = AgeRule(max_age=27)
    p = CandidateProfile(age=0, qualification="graduate", category="SC", pwd=True)
    assert effective_max_age(rule, p) == 42


def test_ur_candidate_over_age_is_out_but_sc_is_in():
    n = _notif()
    ur = match_post(n, n.posts[0], CandidateProfile(age=30, qualification="graduate", category="UR"), TODAY)
    sc = match_post(n, n.posts[0], CandidateProfile(age=30, qualification="graduate", category="SC"), TODAY)
    assert not ur.eligible and sc.eligible


def test_under_min_age_fails():
    n = _notif()
    m = match_post(n, n.posts[0], CandidateProfile(age=17, qualification="graduate"), TODAY)
    assert not m.eligible and any(r.rule == "age" and not r.passed for r in m.reasons)


def test_required_stream_blocks_wrong_degree():
    n = _notif(posts=[Post(post_name="Junior Engineer", min_qualification="graduate", required_streams=["engineering"])])
    ba = match_post(n, n.posts[0], CandidateProfile(age=24, qualification="graduate", streams=["arts"]), TODAY)
    btech = match_post(n, n.posts[0], CandidateProfile(age=24, qualification="graduate", streams=["engineering"]), TODAY)
    assert not ba.eligible and btech.eligible


def test_closed_deadline_fails():
    n = _notif(apply_end=date(2026, 10, 1))
    m = match_post(n, n.posts[0], CandidateProfile(age=24, qualification="graduate"), TODAY)
    assert not m.eligible and m.reasons[0].rule == "deadline" and not m.reasons[0].passed


def test_gender_and_state_restrictions():
    n = _notif(posts=[Post(post_name="Constable (Female)", min_qualification="12th", gender_restriction="female", states=["Uttar Pradesh"])])
    ok = match_post(n, n.posts[0], CandidateProfile(age=20, qualification="12th", gender="female", state="Uttar Pradesh"), TODAY)
    wrong_state = match_post(n, n.posts[0], CandidateProfile(age=20, qualification="12th", gender="female", state="Bihar"), TODAY)
    male = match_post(n, n.posts[0], CandidateProfile(age=20, qualification="12th", gender="male", state="Uttar Pradesh"), TODAY)
    assert ok.eligible and not wrong_state.eligible and not male.eligible


def test_match_all_sorts_eligible_first_then_deadline():
    early = _notif(slug="a", apply_end=date(2026, 10, 20))
    late = _notif(slug="b", apply_end=date(2026, 11, 20))
    closed = _notif(slug="c", apply_end=date(2026, 9, 1))
    out = match_all([late, closed, early], CandidateProfile(age=24, qualification="graduate"), TODAY)
    assert [m.notification_slug for m in out] == ["a", "b", "c"]
