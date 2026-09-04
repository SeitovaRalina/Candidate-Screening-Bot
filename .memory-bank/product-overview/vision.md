# Vision

## Purpose

Telegram bot that screens a candidate before a technical interview: compares a resume against a vacancy and produces a candidate card with a recommendation, evidence, and interview questions. Goal is to save recruiter time on first-pass screening while keeping the accept/reject decision with a human.

## Users

- Recruiter — sends vacancy + resume, receives the card, decides whether to invite the candidate.
- Technical interviewer — receives the card's "recommended questions" section to prepare for the interview.

## Input

- Vacancy: link (hh.ru at minimum; other sources possible) or pasted text.
- Resume: **file** (per client, 2026-09-04 meeting) — format not yet confirmed (see open questions). Earlier working assumption was plain text; superseded by transcript.

## Output — candidate card

1. Verdict: fit / not fit, invite to technical interview or not.
2. Criteria behind the verdict, with quotes/evidence from the resume — client explicitly does not want a black-box score.
3. Red flags found (see requirements/candidate-screening-criteria.md).
4. Recommended interview questions for the technical interviewer.

## MVP boundary

In scope:
- Single candidate per request (vacancy + resume in, card out).
- hh.ru public vacancy parsing by link — reads the public vacancy webpage's embedded JSON-LD (`schema.org/JobPosting`), not the api.hh.ru endpoint, which closed unauthorized access in April 2026 (D-9 → fixed by D-10). No login needed; verified against a real live vacancy. Pasted vacancy text is also fully supported as an alternative.
- Structured verdict + evidence + red flags + questions.

Out of scope (phase 2 / needs separate client sign-off):
- hh.ru login for hidden/direct vacancies (personal account — legal/ToS + guardrail review required, see open questions).
- Batch screening of multiple candidates.
- Vacancy sources other than hh.ru.

## Human-in-the-loop boundary

The bot evaluates autonomously (no human needed to steer the analysis step), but the **final invite/reject decision stays with the recruiter** — the bot's verdict is a recommendation with evidence, not an autonomous rejection action. This matches the client's own requirement ("не хотим слепо доверять ИИ") and the hiring-decision guardrail (кадровое решение = requires human approval).
