# Decisions

## D-1 — Architecture: managed workflow with LLM steps, not a freely-exploring agent
The process path is known in advance (parse vacancy -> parse resume -> compare -> flag -> card). Called "agent" to the client colloquially; built and evaluated as a workflow. See `tech-details/stack.md`.
**Date:** 2026-09-04.

## D-2 — Channel: Telegram via Hermes Messaging Gateway
Per playbook default; avoids hand-rolling bot infrastructure. Confirmed by client interest in "рассматривается возможность использования бота в Telegram."
**Date:** 2026-09-04.

## D-3 — Human keeps the final hiring decision
Transcript Тема 4 confirms explicitly: "окончательное решение о приглашении на собеседование остаётся за человеком" and the human "будет проверять и подтверждать решения нейросети." The bot runs its analysis autonomously (no human needed to steer the analysis step itself), but its verdict is advisory. This resolves the apparent tension with Тема 3's "оценка резюме без первичного участия человека" — that line describes the analysis step, not the final decision.
**Date:** 2026-09-04.

## D-4 — Every verdict/red-flag must cite resume evidence
Client requirement, stated twice in the transcript (Тема 3 and Тема 4): must be able to explain decisions by quoting the resume/vacancy. Non-negotiable design constraint, not a nice-to-have.
**Date:** 2026-09-04.

## D-5 — hh.ru personal-account login excluded from MVP
Regardless of technical feasibility findings from OQ-5, personal-account login is out of MVP scope pending explicit client approval and guardrail review. See `open-questions.md` OQ-5 and `product-overview/anti-stories.md`.
**Date:** 2026-09-04.

## D-6 — Candidate card restructured to green flags / red flags
Replaces the earlier "criteria + separate red flags" split with a single symmetric list, each item with a resume quote. Matches the client's own wording in the transcript ("список несоответствий/соответствий") more literally than the original draft. Criteria set expanded beyond the meeting's narrow examples via market research (see `tech-details/existing-solutions.md` and `product-overview/requirements/candidate-screening-criteria.md`) at the client's explicit request for a "universal" solution.
**Date:** 2026-09-04.

## D-7 — Runtime: plain Python Telegram bot, not Hermes (supersedes D-2's implicit assumption)
D-2 named Hermes as the channel per playbook default. Hermes is Effective's internal messaging-gateway product and is not available in this build environment, and the demo is time-boxed to the same day. Built instead as a plain Python bot (`python-telegram-bot`) calling the Anthropic API directly. This is a documented deviation, not a silent one — revisit for production handoff, since Hermes would be the correct default once available (attachments, session restart, cron already solved there).
**Date:** 2026-09-04.

## D-8 — Harness installed manually, not via `/setup`'s interactive flow
Copied `.claude/{agents,skills,hooks,lib,terse}`, `AGENTS.md`, `.assistant/INVARIANTS.md` by hand from the harness checkout and generated `.harness-lock` with a script, skipping `/setup`'s 6-question interview to save time under the hard deadline (answers were already known from this conversation: PROJECT_TYPE 1, stack backend-python, no omp, existing memory bank preserved). The harness checkout itself has no `.git` at install time, so `.harness-lock`'s `harness_source`/`commit_sha` are placeholder values instead of a pinned `<remote>@<sha>` — `/sync` cannot be run against this lock until the harness checkout gets a real git remote+commit. Flagged in `CLAUDE.md`.
**Date:** 2026-09-04.

## D-9 — hh.ru API returns 403 for unauthorized requests, even public single-vacancy GET
Verified live (2026-09-04): `GET api.hh.ru/vacancies` and `GET api.hh.ru/vacancies/{id}` both return `403 {"errors":[{"type":"forbidden"}]}` regardless of User-Agent. Web research confirms hh.ru closed unauthorized public API access starting April 2026 — this is not specific to hidden/direct vacancies (OQ-5's original scope), it affects the "public vacancy, no login" MVP path this project was scoped around from the start. Superseded same-day by D-10 (source switched, not blocked).
**Date:** 2026-09-04.

## D-10 — hh.ru link support fixed: read the public vacancy webpage's JSON-LD, not api.hh.ru
Verified live (2026-09-04): `https://hh.ru/vacancy/{id}` (the normal public webpage, not the API) returns 200 with no login required, and `robots.txt` disallows `/auth`, `/login`, `/account`, `/resume` but not `/vacancy` — this is public content, not gated data. The page embeds a `schema.org/JobPosting` JSON-LD block (put there for search-engine indexing — i.e. meant to be machine-read), which `vacancy.py` now parses instead of calling api.hh.ru. This is explicitly NOT the personal-account-login path excluded by anti-stories.md/D-5: no credentials, no session, just an unauthenticated GET on a page hh.ru serves to anyone. It does not solve hidden/direct vacancies (those still need a real authenticated session or a registered API app — OQ-5's login/API-app question stands for that case only). Confirmed end-to-end against a real live vacancy (Sber, id 130846752).
**Date:** 2026-09-04.

## D-11 — Resume input: support both file and text, no priority decision needed
Anton's reply to `communications/2026-09-04-kickoff-followup.md` item 1 (2026-09-04): recruiters normally send either an hh.ru link or a PDF file; wants both accepted for MVP, delegated the "which is simpler to build first" call to Ralina ("решай сама, что проще для прототипа"). Resolves OQ-1. No build decision actually needed — `resume_extract.py`/`bot.py` already accept PDF/DOCX/TXT files and plain text as equally valid input paths; both existed before this reply.
**Date:** 2026-09-04.

## D-12 — hh.ru scope confirmed public-only; new UX requirement for inaccessible vacancies
Anton's reply, item 2: confirms personal-account login is a separate story (matches D-5) and public vacancies are the right MVP scope (matches D-10). New requirement: when a vacancy can't be parsed (closed/private/etc.), the reply must lead with the exact phrase "Вакансия недоступна для парсинга" rather than a generic technical error — implemented in `bot.py`'s `VacancyFetchError` handler. Client also re-confirmed pasting vacancy text as a wanted input path (already built) and suggested testing against a few real open vacancies before the demo.
**Date:** 2026-09-04.

## D-13 — Statelessness confirmed: zero cross-candidate memory in production
Anton's reply, item 3: each candidate is an independent session, the bot must forget everything after producing a card, no exceptions. Local debug logging is permitted only on Ralina's own machine, never in a deployed instance. Already matches the existing design (`bot.py`'s `_reset_pending` clears all per-chat state right after the card is sent) — no architecture change needed. Interpreted "no memory" as no persistence beyond one request's lifecycle, not "hold nothing in a Python variable while processing" (which would be impossible) — this interpretation is recorded explicitly rather than assumed silently.
**Date:** 2026-09-04.

## D-14 — Zero resume storage anywhere, even temporarily (stronger than originally scoped)
Anton's reply, item 4: no storage in a database, no storage in logs, nowhere, not even temporarily, in the production build — driven by PII fear, stated explicitly twice. Local storage is permitted only on Ralina's own machine for testing. Implemented as `LOCAL_DEBUG_LOGGING` (`config.py`, default `false`): production logging carries only counts/verdicts/generic events, never vacancy titles or resume content; full detail logging is opt-in for local dev only. Audited (2026-09-04): no code path writes an uploaded resume to disk (PDF/DOCX extraction runs from an in-memory `BytesIO`, never a temp file) and no code path persists resume/vacancy/card content to a database — none exists in this project.
**Date:** 2026-09-04.

## D-15 — Single vacancy+resume pair per session, strict 1:1 (no batch, no multi-vacancy matching)
Anton's reply, items 5 and 6: exactly one resume + one vacancy per screening request for MVP; no batch input, and no "one resume against several vacancies" matching mode ("в будущем, может быть... но сейчас не надо"). Matches the already-built pairing logic in `bot.py` — no change needed.
**Date:** 2026-09-04.

## D-16 — Human-in-the-loop framing explicitly validated by the client
Anton's reply closing note: "особенно понравилось, что ты отделила, что бот делает сам, а что я решаю" — upgrades D-3 from Ralina's reading of an ambiguous transcript to an explicitly client-confirmed design choice. No change to D-3's substance, just recording the confirmation.
**Date:** 2026-09-04.
