# Candidate Screening Bot

A Telegram bot that screens a candidate's resume against a job vacancy before a technical interview, and returns a structured candidate card — verdict, evidence-backed green/red flags, and targeted interview questions.

Built for Anton (Effective client) as a same-day MVP prototype, 2026-09-04.

## Try it now

**[@candidate_screening_ai_bot](https://t.me/candidate_screening_ai_bot)** on Telegram.

1. Send the vacancy — an hh.ru link or plain text.
2. Send the candidate's resume — a PDF/DOCX/TXT file or plain text.
3. Order doesn't matter, and both can be sent together in one message. The bot tells you what it understood at each step.

You'll get back a card: verdict (fit / not fit / unclear), green flags and red flags each with a verbatim quote from the resume or vacancy, and a handful of interview questions targeted at this specific candidate's gaps.

## What it does and doesn't do

- **Recommends, never decides.** The verdict is advisory — the human recruiter always makes the final call.
- **Every flag is evidence-backed.** No claim in the card is allowed without a real quote from the resume/vacancy; a flag the model can't cite for is dropped rather than shown.
- **No data is stored.** A resume is processed in memory for the one request and then forgotten — no database, no file, no log of its content. Each candidate is a fully independent session.
- **Checks are layered.** Deterministic code (date-overlap in employment history, unexplained gaps, AI-generated-text pattern) runs first and is always included in the card; an LLM comparison against the vacancy adds judgment-based findings (skill/title mismatch, relevance) on top.

## Project layout

- `prototype/` — the actual bot (`prototype/README.md` has setup, testing, and deployment details)
- `.memory-bank/` — product vision, screening criteria, architecture rationale
- `.assistant/decisions.md` — append-only log of every design decision and why, in order
- `.assistant/open-questions.md` — items still pending Anton's confirmation
- `communications/` — messages sent to the client, kept for scope-dispute reference

## Status

Working prototype, deployed and demoed. Not yet an MVP handoff — see `.assistant/open-questions.md` and `prototype/README.md`'s "Known outstanding items" for what's still open (client confirmations pending, a couple of small UX gaps, and the client's own 5 real test cases still owed).
