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

## D-17 — LLM calls routed through Effective's internal LiteLLM gateway, not api.anthropic.com directly
Ralina's own infra requirement (2026-09-04, not from Anton): `screening.py` now calls `anthropic.Anthropic(base_url=LITELLM_BASE_URL)` with `LITELLM_BASE_URL` defaulting to `https://llm.effective.land/anthropic` (LiteLLM's Anthropic-passthrough route — the SDK appends `/v1/messages` itself, per [LiteLLM docs](https://docs.litellm.ai/docs/pass_through/anthropic_completion)). `ANTHROPIC_API_KEY` now holds the gateway's virtual key, not a personal Anthropic key. Setting `LITELLM_BASE_URL=` empty falls back to calling Anthropic directly, kept as an escape hatch. **Not yet verified against the real gateway** (no virtual key available at edit time) — the exact model alias the gateway expects for `ANTHROPIC_MODEL` is unconfirmed; verify both before the demo.
**Date:** 2026-09-04.

## D-18 — 5 self-sourced manual test pairs added; found and fixed a real em-dash false-positive bug in the AI-text heuristic
Anton's own 5 real resume+vacancy pairs (kickoff-followup item 7) are still outstanding, so Ralina built a stopgap set herself: 5 real, live, public hh.ru vacancy links (verified against `vacancy.py`'s actual fetch code, not just eyeballed) paired with synthetic-but-realistic resumes she authored (not scraped real candidates — see the honesty note in `prototype/tests/manual_cases/README.md` for why scraping real hh.ru resumes would itself violate the client's own PII stance, D-14, before the bot even exists). Each pair targets one scenario from `candidate-screening-criteria.md`: good fit, employer date overlap, skill/title mismatch (LLM-only), education/work overlap + gap together, AI-generated-sounding text.
Building case 5 surfaced a real bug: `check_ai_generated_text_pattern` counted em-dashes used as `"2020 — 2024"` date-range separators toward its dash-density signal, so almost any resume using that (very common RU-resume) date format false-triggered the flag on 2-4 dashes alone (cases 1-4 all falsely fired before the fix). Fixed in `deterministic_checks.py`: em-dashes inside a matched `_YEAR_RANGE_RE` span are now excluded from the count before computing the rate. Added `test_no_ai_flag_on_em_dash_date_ranges` as a regression test (existing fixtures all used a plain hyphen, which is why this wasn't caught earlier). These 5 pairs remain a smoke-test supplement, not a replacement for Anton's real acceptance set.
**Date:** 2026-09-04.

## D-19 — LiteLLM base_url corrected: root `/v1/messages`, not `/anthropic` passthrough
Live-tested (2026-09-04): `LITELLM_BASE_URL=https://llm.effective.land/anthropic` returned `404 Not Found` from `POST .../anthropic/v1/messages` — this gateway does not have the Anthropic provider-passthrough route enabled (that's a separate, opt-in LiteLLM feature, distinct from its own unified Anthropic-format endpoint). Fixed default to `https://llm.effective.land` (no suffix) so the SDK's own `/v1/messages` append hits LiteLLM's root unified endpoint instead, which works regardless of the backing model provider. Superseds D-17's default. Still unverified whether `ANTHROPIC_MODEL=claude-sonnet-5` is a model alias this gateway actually serves — that's the next thing to check if the retry produces a different (non-404) error.
**Date:** 2026-09-04.

## D-20 — Small-talk short-circuit added; the bot is a workflow, not a chat agent, and now says so upfront
Manual testing (2026-09-04) surfaced a UX gap the client will hit immediately in a demo: `bot.py`'s `handle_message` is pure slot-filling (D-1's deterministic-workflow design) — any text goes straight into the empty vacancy or resume slot with zero interpretation, so "Привет! Что ты можешь?" was silently swallowed as "vacancy text" and got the generic "жду резюме" reply instead of an answer. Not a bug in the pipeline itself, but a bad first impression. Fix: `_looks_like_small_talk()` in `bot.py` — a short keyword/phrase check (not an LLM call, keeps the "no free-text intent routing" design intact) that only fires when both slots are still empty and the message is short (≤80 chars, a real pasted vacancy/resume essentially never is), and re-sends the `/start` greeting instead of consuming the message. Deliberately narrow: this is not a general chit-chat handler, just coverage for the one phrase a client predictably tries. Unit-tested in `tests/test_bot.py`.
**Date:** 2026-09-04.

## D-21 — Strict two-step flow (vacancy first, then resume), replacing "any order" — fixes a silent-wrong-answer bug, not just a UX complaint
Ralina reported (2026-09-04) that the two-message flow "не интуитивно понятно". Investigation found a real correctness bug behind the UX complaint, not just unclear copy: the old design accepted vacancy-text and resume-text "in any order", but had **no way to tell them apart** — whichever plain-text message arrived first was unconditionally treated as the vacancy (`vacancy.py`'s `fetch_vacancy()` accepts arbitrary text as a valid vacancy description with no validation), so a user sending the resume text first got a card built from swapped inputs with **no error at all**. Fixed: `bot.py` now enforces vacancy-first, fetches and confirms it immediately (`✅ Вакансия принята: {title}`) before asking for the resume, so the user gets visible proof of what was understood at each step and a vacancy-fetch error surfaces immediately rather than after the resume is already in. Trades the (illusory, already-broken) "any order" flexibility for correctness + a guided `/start` message with numbered steps.
**Date:** 2026-09-04.

## D-22 — Combined single-message input accepted (vacancy + resume together)
User request (2026-09-04, mid-review of D-21): "а вдруг человек захочет в одном сообщении все кинуть? Агент тоже должен это принять." Added `_try_split_combined_message()` in `bot.py`: a best-effort, non-LLM heuristic that looks for a resume-section header (reusing `deterministic_checks.py`'s own header vocabulary) appearing after a vacancy-marker keyword or hh.ru link, or an hh.ru link followed by a long freeform remainder — and screens immediately if it finds one, without waiting for a second message. Also handles a resume **file** sent with the vacancy text as its Telegram caption. Deliberately conservative (requires a vacancy-marker word before the resume header) specifically so a resume sent *alone* doesn't get its own name/education block wrongly carved off as a fake vacancy — verified in `tests/test_bot.py` that both a lone resume and a lone vacancy correctly return "no split" and fall through to the normal single-item path. Known blind spot, accepted for a same-day prototype: a resume that happens to mention a vacancy-sounding word (e.g. "обязанности" describing a past job) before its own experience section could still misfire — not silent data loss either way, both halves are still used as *something*, just possibly swapped.
**Date:** 2026-09-04.
