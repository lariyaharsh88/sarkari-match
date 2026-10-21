---
title: "An eligibility engine for Indian government jobs"
slug: "sarkari-match"
summary: "TODO one sentence with the three headline numbers: extraction accuracy, matcher precision, organic sessions."
role: "Solo builder: product, data pipeline, evals, web"
timeline: "Oct 2026 – TODO"
tags: ["0→1", "LLM extraction", "Evals", "Programmatic SEO"]
status: "draft"
metrics:
  - { value: "TODO%", label: "field-level extraction accuracy on N hand-labelled notifications" }
  - { value: "TODO% / TODO%", label: "matcher precision / recall on N judged profiles" }
  - { value: "TODO", label: "notifications live across N boards" }
  - { value: "TODO", label: "organic clicks, last 28 days" }
---

## TL;DR
Candidates for government jobs read dozens of notification PDFs to answer one question: which of these can I apply for? I built a pipeline that turns official PDFs into validated structured records, a rules engine that answers that question with the exact rule behind every verdict, and a site with one page per notification. Every number below comes from `docs/metrics-log.csv` and `evals/results/`.

## The problem
TODO. Quote the search volume for a few "eligibility" queries from the keyword tool, and describe what the top-ranking pages actually give the user.

## Why extraction accuracy is the product
A wrong age cap or missing relaxation sends a candidate to the wrong answer. So the first week went into a 50-notification gold set and a field-level eval, not into the UI.

<Compare before="TODO% (first prompt)" after="TODO% (shipped)" label="Field-level extraction accuracy" />

TODO: the two or three worst fields at the start, what caused them (scanned PDFs, Hindi-only tables, category-wise vacancy tables), and what fixed them.

## The validation gate
TODO: how many extractions were rejected or held for review in the first month, what the most common reasons were, and one example that would have published a wrong deadline.

## The eligibility engine
TODO: the rule set, the additive relaxation decision, and one real mistake the matcher eval caught in a hand-judged profile.

## Distribution and results
TODO: pages indexed over time, clicks and impressions by page type (notification, board, qualification), eligibility checks run.

## What I'd do differently
TODO, in your own words, only what is true.
