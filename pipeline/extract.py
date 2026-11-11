"""PDF text -> Notification via Gemini structured output.

Usage:  python -m pipeline.extract data/pdfs/abc.pdf --board SSC --source-url https://... --pdf-url https://...
Needs GEMINI_API_KEY in the environment or .env. Model is configurable with GEMINI_MODEL.
"""
import argparse
import json
import os
import re
from datetime import date
from pathlib import Path
from typing import Optional

import pdfplumber
from dotenv import load_dotenv
from pydantic import ValidationError

from engine.schema import Notification

load_dotenv()

MAX_CHARS = 60_000  # notifications beyond this are truncated to the first pages, which hold the key facts

PROMPT = """You are extracting structured facts from an official Indian government job notification.
Return ONLY JSON matching the schema. Rules:
- Dates as YYYY-MM-DD. If a date is missing, use null. Never guess a date.
- min_qualification must be one of: 8th, 10th, 12th, iti, diploma, graduate, postgraduate, phd.
  Pick the LOWEST level that satisfies the post. Put the verbatim wording in qualification_text.
- required_streams: only when the degree must be in a specific field (engineering, law, commerce, medicine, agriculture, computer_science, pharmacy, nursing, education). Else empty list.
- age.relaxation_years: only categories the PDF states explicitly, keys OBC, SC, ST, PWD, EX_SERVICEMAN, WOMEN.
- fee_by_category: integer rupees per category key (UR, OBC, EWS, SC, ST, PWD, WOMEN). 0 means exempt.
- One Post per distinct post name. Merge category-wise vacancy rows into vacancies_by_category.
- confidence: for each of title, apply_end, posts, fee_by_category give 0-1 how sure you are.
- board is given to you; copy it. slug: lowercase-hyphenated from board, exam name and year.
Text of the notification follows.
"""


def pdf_text(path: Path, max_chars: int = MAX_CHARS) -> str:
    chunks = []
    total = 0
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            chunks.append(t)
            total += len(t)
            if total > max_chars:
                break
    text = "\n\n".join(chunks)
    return text[:max_chars]


def slugify(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:80]


def extract(text: str, board: str, source_url: str, pdf_url: Optional[str] = None) -> Notification:
    from google import genai  # imported lazily so the web app never needs the SDK

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    # response_json_schema takes standard JSON Schema ($defs, additionalProperties),
    # so the pydantic schema goes in unmodified.
    schema = Notification.model_json_schema()
    resp = client.models.generate_content(
        model=model,
        contents=f"{PROMPT}\nboard: {board}\nsource_url: {source_url}\npdf_url: {pdf_url or ''}\n\n{text}",
        config={"response_mime_type": "application/json", "response_json_schema": schema, "temperature": 0},
    )
    data = json.loads(resp.text)
    data["board"] = board
    data["source_url"] = source_url
    data["pdf_url"] = pdf_url
    data["extracted_at"] = date.today().isoformat()
    data["is_sample"] = False
    if not data.get("slug"):
        data["slug"] = slugify(f"{board}-{data.get('title','')}")
    try:
        return Notification(**data)
    except ValidationError as e:
        raise RuntimeError(f"Gemini output failed schema validation: {e}") from e


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--board", required=True)
    ap.add_argument("--source-url", required=True)
    ap.add_argument("--pdf-url")
    args = ap.parse_args()
    n = extract(pdf_text(Path(args.pdf)), args.board, args.source_url, args.pdf_url)
    print(n.model_dump_json(indent=2))
