# Labelling gold notifications

`scripts/scaffold_gold.py` downloads real PDFs and writes one blank file per PDF to `gold/todo/`. Each file names its PDF in `_local_pdf`.

## Per file (aim for 5–8 minutes)
1. Open the PDF named in `_local_pdf`.
2. **Not a recruitment notice** (result, corrigendum, admit card, tender)? Set `_skip_reason` (e.g. `"result"`) and leave the file in `todo/`. Skips count too, because triage accuracy matters as well.
3. Otherwise fill in what the PDF says, and **nothing it doesn't**. Leave a field `null` or empty if the PDF is silent. Never use your own knowledge.
   - Dates: `YYYY-MM-DD`.
   - `fee_by_category` keys: `UR OBC EWS SC ST PWD WOMEN`, values in ₹.
   - `min_qualification`: one of `8th 10th 12th iti diploma graduate postgraduate phd`.
   - `relaxation_years` keys: `OBC SC ST PWD EX_SERVICEMAN WOMEN`.
   - `max_age` is the **unreserved** upper limit.
   - Add one `posts` entry per post with different eligibility. Posts with identical rules can share an entry.
4. Move the finished file up one level: `git mv` or drag it from `gold/todo/` to `gold/`.

## Then
```
python scripts/predict_gold.py        # needs GEMINI_API_KEY
python evals/run_extraction_eval.py
```
Once you have 10 real gold files, delete the two `sample-*.json` files.
