"""PDF text -> Notification via Gemini structured output.

Usage:  python -m pipeline.extract data/pdfs/abc.pdf --board SSC --source-url https://... --pdf-url https://...
Needs GEMINI_API_KEY in the environment or .env. Model is configurable with GEMINI_MODEL.
"""
import argparse
import json
import time
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
- If the document is not a recruitment notification (corrigendum, result, admit card, schedule, general notice), return posts as an empty list.
The notification follows (as an attached PDF and/or its extracted text).
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


GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MAX_CHARS = 16000  # free-tier tokens-per-minute caps are low; eligibility is near the top anyway
# Tried in order; a model that is missing (404) or whose per-minute cap is smaller than the request (413) is skipped.
GROQ_MODELS = ["meta-llama/llama-4-scout-17b-16e-instruct", "llama-3.3-70b-versatile", "openai/gpt-oss-120b"]


def is_quota_error(e: Exception) -> bool:
    m = str(e)
    return "429" in m or "RESOURCE_EXHAUSTED" in m or "quota" in m.lower()


def _groq_json(prompt: str, schema: dict) -> str:
    """Fallback for text PDFs when Gemini's free quota is used up. Groq is OpenAI-compatible."""
    import httpx
    models = [os.environ["GROQ_MODEL"]] if os.environ.get("GROQ_MODEL") else GROQ_MODELS
    messages = [
        {"role": "system", "content": "Reply with one JSON object that validates against this JSON Schema:\n" + json.dumps(schema, separators=(",", ":"))},
        {"role": "user", "content": prompt},
    ]
    last = ""
    for model in models:
        for attempt in range(3):
            r = httpx.post(GROQ_URL, timeout=120, headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
                           json={"model": model, "temperature": 0, "response_format": {"type": "json_object"}, "messages": messages})
            if r.status_code < 300:
                return r.json()["choices"][0]["message"]["content"]
            last = f"Groq {model} {r.status_code}: {r.text[:200]}"
            if r.status_code == 429 and "per day" not in r.text and attempt < 2:
                time.sleep(65)  # per-minute token window
                continue
            break
        if r.status_code not in (400, 404, 413):  # only move on for model-specific problems
            break
    raise RuntimeError(last)


def extract(text: str, board: str, source_url: str, pdf_url: Optional[str] = None,
            pdf_bytes: Optional[bytes] = None) -> Notification:
    """pdf_bytes is for scanned PDFs with no text layer: Gemini reads the pages itself.
    If Gemini's quota is exhausted and GROQ_API_KEY is set, text PDFs fall back to Groq."""
    schema = Notification.model_json_schema()
    head = f"{PROMPT}\nboard: {board}\nsource_url: {source_url}\npdf_url: {pdf_url or ''}\n\n"
    try:
        raw = _gemini_json(head + text, schema, pdf_bytes)
    except Exception as e:  # noqa: BLE001
        if not (is_quota_error(e) and os.environ.get("GROQ_API_KEY") and not pdf_bytes):
            raise
        print(f"[extract] Gemini quota hit, using Groq for {pdf_url}")
        raw = _groq_json(head + text[:GROQ_MAX_CHARS], schema)
    data = json.loads(raw)
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
        raise RuntimeError(f"LLM output failed schema validation: {e}") from e


def _gemini_json(prompt: str, schema: dict, pdf_bytes: Optional[bytes]) -> str:
    from google import genai  # imported lazily so the web app never needs the SDK
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    model = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
    # response_json_schema takes standard JSON Schema ($defs, additionalProperties),
    # so the pydantic schema goes in unmodified.
    for attempt in range(4):  # 503 "high demand" is common and clears within a minute or two
        try:
            resp = client.models.generate_content(
                model=model,
                contents=([types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")] if pdf_bytes else [])
                + [prompt],
                config={"response_mime_type": "application/json", "response_json_schema": schema, "temperature": 0},
            )
            break
        except Exception as e:  # noqa: BLE001
            if attempt == 3 or not any(c in str(e) for c in ("503", "UNAVAILABLE", "500 ")):
                raise
            time.sleep(15 * (attempt + 1))
    return resp.text


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--board", required=True)
    ap.add_argument("--source-url", required=True)
    ap.add_argument("--pdf-url")
    args = ap.parse_args()
    n = extract(pdf_text(Path(args.pdf)), args.board, args.source_url, args.pdf_url)
    print(n.model_dump_json(indent=2))
