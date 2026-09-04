<!-- Manual/end-to-end test cases, self-sourced by Ralina (2026-09-04) while
     Anton's own 5 real cases (kickoff-followup item 7) are still pending.

     Honesty note on "real": the vacancies below are real, live, public hh.ru
     postings (verified against prototype/vacancy.py's actual fetch code, not
     just eyeballed - see the check script output referenced in
     .assistant/decisions.md D-18). The resumes are NOT scraped real
     candidates - hh.ru resumes require a login to view (the exact
     personal-account access this project deliberately excludes, D-5), and
     scraping a real stranger's PII to build a test fixture would contradict
     the client's own zero-storage/PII stance (D-14) before the bot even
     exists. Instead these are synthetic-but-realistic resumes, each written
     to deliberately exercise one scenario from
     .memory-bank/product-overview/requirements/candidate-screening-criteria.md
     with a known expected outcome, so a wrong bot answer is easy to spot.
     Replace/supplement with Anton's real pairs once they arrive - those
     remain the actual acceptance set (see stack.md's eval methodology). -->

# Manual test cases (self-sourced, 2026-09-04)

Run each pair through the running bot (`python main.py`, send the vacancy link then the resume text, or vice versa) and compare the card against "Expected" below. These are smoke tests for the pipeline, not a substitute for Anton's own 5 real cases (still outstanding — see `communications/2026-09-04-anton-reply-kickoff-followup.md` footer).

## Case 1 — Good fit, junior
**Vacancy:** https://hh.ru/vacancy/130056956 (Python-разработчик Junior, StafIT)
**Resume:** `case-1-good-fit-resume.txt`
**Expected:** verdict `fit` or `unclear` leaning positive. No deterministic red flags (no date overlaps, no gaps, clean text). Green flag for higher education present (per the education-as-green-flag resolution, OQ-2/D-2-criteria-doc).

## Case 2 — Employer date overlap (deterministic red flag)
**Vacancy:** https://hh.ru/vacancy/133660218 (Middle/Senior Python-разработчик, ИЦ АЙ-ТЕКО)
**Resume:** `case-2-employer-overlap-resume.txt`
**Expected:** `check_employer_date_overlap` fires — two jobs listed as `2021 — 2024` and `2022 — н.в.` (3-year overlap). Card's red flags must include this, verbatim quote, `source=deterministic` (rendered with the `[code]` marker in `card.py`).

## Case 3 — Skill/title mismatch (LLM-judgment red flag, not deterministic)
**Vacancy:** https://hh.ru/vacancy/131921142 (Python / ML Engineer, Фармстандарт.ИТ)
**Resume:** `case-3-skill-mismatch-resume.txt`
**Expected:** no deterministic flags should fire (dates are clean). The LLM step should flag the title/stack mismatch (candidate's actual experience is PHP/WordPress sites, resume claims "ML Engineer" with no ML framework, dataset, or model ever named) — tests that `screening.py`'s prompt catches this even though no regex can.

## Case 4 — Education/work overlap + unexplained gap (two deterministic checks at once)
**Vacancy:** https://hh.ru/vacancy/132851810 (Fullstack/Backend NodeJS/Python developer, ПартДизайн)
**Resume:** `case-4-edu-work-overlap-gap-resume.txt`
**Expected:** `check_education_work_overlap` fires (full-time job starts 2 years before university graduation) AND `check_unexplained_gaps` fires (2-year employment gap, 2020-2022, with no explanation in the text). Both should show up as separate red flags with distinct quotes.

## Case 5 — AI-generated-sounding text (lexical heuristic red flag)
**Vacancy:** https://hh.ru/vacancy/135006595 (Middle/Senior Python разработчик, Сбер.IT)
**Resume:** `case-5-ai-generated-text-resume.txt`
**Expected:** `check_ai_generated_text_pattern` fires (buzzword density + em-dash rate over threshold). Per the criteria doc, this must render as a soft flag ("не повод для отказа само по себе") — verify the card's wording doesn't read as an automatic rejection, and that the LLM step doesn't escalate it into `verdict=not_fit` on this signal alone.

## How to re-verify a vacancy link still resolves
```bash
cd prototype
.venv/Scripts/python -c "
import asyncio, vacancy
asyncio.run(vacancy._fetch_from_public_page('130056956', source_url='https://hh.ru/vacancy/130056956'))
"
```
Replace the id; a live vacancy prints without raising. hh.ru vacancies do get taken down over time (some of the 5 above were already showing as "архив" in search results on 2026-09-04, but the public page + JSON-LD were still live when checked — re-verify close to the actual demo).
