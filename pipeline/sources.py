"""Official notification sources.

Only official board pages. Each source yields candidate PDF links; the fetcher
downloads anything new. Add a board by adding one entry. Selectors are kept
loose on purpose: government sites change layout without notice, and the
validation gate downstream catches garbage.
"""
from typing import Dict, List

SOURCES: List[Dict[str, str]] = [
    # board, listing page, substring a link must contain to be considered a notification
    # SSC is crawled through its JSON API (fetch.discover_ssc), not here.
    {"board": "UPSC", "url": "https://upsc.gov.in/examinations/active-examinations", "must_contain": ".pdf"},
    {"board": "UPSC", "url": "https://upsc.gov.in/recruitment/advertisements", "must_contain": ".pdf"},
    {"board": "IBPS", "url": "https://www.ibps.in/", "must_contain": ".pdf"},
    {"board": "SBI", "url": "https://sbi.co.in/web/careers/current-openings", "must_contain": ".pdf"},
    # SSC and UPPSC have their own crawlers in fetch.py (JSON API / ASP.NET session).
    {"board": "BPSC", "url": "https://bpsc.bihar.gov.in/", "must_contain": ".pdf"},
]
# RRB regional sites serve TLS certificates for the wrong hostname, so they are not crawled.
# MPSC's API requires a signed request header (deliberate anti-scraping), so it is left out. UPSC times out from GitHub's US runners.

USER_AGENT = "sarkari-match/0.1 (+personal research project; polite crawler, 1 req/2s)"
