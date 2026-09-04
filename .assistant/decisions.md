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
Verified live (2026-09-04): `GET api.hh.ru/vacancies` and `GET api.hh.ru/vacancies/{id}` both return `403 {"errors":[{"type":"forbidden"}]}` regardless of User-Agent. Web research confirms hh.ru closed unauthorized public API access starting April 2026 — this is not specific to hidden/direct vacancies (OQ-5's original scope), it affects the "public vacancy, no login" MVP path this project was scoped around from the start. `vacancy.py` now raises a clear, distinct error on 403 pointing the user at pasting vacancy text instead of a link, rather than silently failing or crashing. OQ-5 upgraded back to blocking/HIGH and reworded — this needs an answer from Anton before the hh.ru-link path can work at all, independent of the personal-login question.
**Date:** 2026-09-04.
