"""Canonical data model for a government job notification.

Everything the pipeline extracts and everything the eligibility engine reads
goes through these models. Python 3.9 compatible (no X | Y unions).
"""
from datetime import date
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

# Ordinal ladder for minimum-qualification checks. A candidate at level N
# satisfies any requirement at level <= N, unless the post requires a
# specific stream (see Post.required_streams).
QUALIFICATION_LEVELS: Dict[str, int] = {
    "8th": 1,
    "10th": 2,
    "12th": 3,
    "iti": 3,
    "diploma": 4,
    "graduate": 5,
    "postgraduate": 6,
    "phd": 7,
}

CATEGORIES = ["UR", "EWS", "OBC", "SC", "ST"]

# Default age relaxations in years when the notification does not state its own.
# Central government norms; many boards restate exactly these.
DEFAULT_AGE_RELAXATION: Dict[str, int] = {
    "OBC": 3,
    "SC": 5,
    "ST": 5,
    "PWD": 10,
    "EX_SERVICEMAN": 3,
}


class AgeRule(BaseModel):
    min_age: Optional[int] = Field(None, description="Minimum age in completed years")
    max_age: Optional[int] = Field(None, description="Maximum age in completed years for the unreserved category")
    as_on: Optional[date] = Field(None, description="Date on which age is reckoned")
    relaxation_years: Dict[str, int] = Field(
        default_factory=dict,
        description="Extra years allowed per category key: OBC, SC, ST, PWD, EX_SERVICEMAN, WOMEN",
    )


class Post(BaseModel):
    post_name: str
    vacancies: Optional[int] = None
    vacancies_by_category: Dict[str, int] = Field(default_factory=dict)
    pay_level: Optional[str] = Field(None, description="e.g. 'Level 4' or '25500-81100'")
    min_qualification: str = Field(..., description="One of QUALIFICATION_LEVELS keys")
    required_streams: List[str] = Field(
        default_factory=list,
        description="Specific streams when the degree must be in a field, e.g. ['engineering', 'law', 'commerce']",
    )
    qualification_text: str = Field("", description="Verbatim qualification wording from the PDF")
    age: AgeRule = Field(default_factory=AgeRule)
    gender_restriction: Optional[str] = Field(None, description="'male', 'female' or null")
    states: List[str] = Field(default_factory=list, description="Empty means open to all states")


class Notification(BaseModel):
    slug: str
    board: str = Field(..., description="Short code: SSC, UPSC, RRB, IBPS, SBI, UPPSC, BPSC, MPSC ...")
    title: str
    advt_no: Optional[str] = None
    source_url: str
    pdf_url: Optional[str] = None
    published_on: Optional[date] = None
    apply_start: Optional[date] = None
    apply_end: Optional[date] = None
    fee_by_category: Dict[str, int] = Field(default_factory=dict, description="Application fee in INR per category")
    posts: List[Post] = Field(default_factory=list)
    total_vacancies: Optional[int] = None
    confidence: Dict[str, float] = Field(default_factory=dict, description="Extractor confidence per top-level field, 0-1")
    needs_review: bool = False
    review_reasons: List[str] = Field(default_factory=list)
    extracted_at: Optional[date] = None
    is_sample: bool = Field(False, description="True for hand-written seed data, never for real extractions")


class CandidateProfile(BaseModel):
    age: int
    qualification: str = Field(..., description="One of QUALIFICATION_LEVELS keys")
    streams: List[str] = Field(default_factory=list, description="e.g. ['engineering'] for a B.Tech holder")
    category: str = "UR"
    gender: Optional[str] = None
    state: Optional[str] = None
    pwd: bool = False
    ex_serviceman: bool = False


class MatchReason(BaseModel):
    rule: str
    passed: bool
    detail: str


class PostMatch(BaseModel):
    notification_slug: str
    board: str
    title: str
    post_name: str
    apply_end: Optional[date]
    eligible: bool
    reasons: List[MatchReason]
