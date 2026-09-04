# Candidate Screening Bot — prototype

Telegram bot: send a vacancy (hh.ru link or pasted text), then a candidate's resume (PDF/DOCX/TXT file, or pasted text) — vacancy first, confirmed immediately, then resume (D-21; not "any order", see decisions.md for why). Vacancy and resume can also be sent together in one message, or a resume file with the vacancy as its caption (D-22). Get back a candidate card (verdict, green/red flags with quotes, interview questions).

This is `prototype/` — the harness's mode-gate sandbox (`.assistant/mode.json` = `prototype`). See `../CLAUDE.md` for the harness install and the Hermes-vs-plain-Python deviation, `../.assistant/decisions.md` for D-1..D-9, `../.assistant/open-questions.md` for what's still pending client confirmation.

## hh.ru vacancy links — how they actually work

hh.ru closed unauthorized `api.hh.ru` access in April 2026 (verified live, D-9) — but `vacancy.py` reads the **public vacancy webpage's** embedded JSON-LD instead (D-10), which needs no login and works today; confirmed against a real live vacancy. Pasting vacancy text directly also works, as an alternative input. Hidden/direct vacancies (not on the public page at all) are still out of scope — see OQ-5.

## Setup

```bash
cd prototype
python -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash; use .venv/bin/activate on Linux/macOS
pip install -r requirements.txt
cp .env.example .env            # fill in TELEGRAM_BOT_TOKEN and ANTHROPIC_API_KEY
python main.py
```

## LLM calls — routed through Effective's LiteLLM gateway

`screening.py` calls the Anthropic SDK with `base_url=LITELLM_BASE_URL` (default `https://llm.effective.land/anthropic`, D-17) instead of talking to `api.anthropic.com` directly. That means:

- `ANTHROPIC_API_KEY` in `.env` must be the gateway's **virtual key**, not a personal `console.anthropic.com` key. Ask whoever admins `llm.effective.land` for one.
- `ANTHROPIC_MODEL` must be a model name/alias the gateway actually serves — verify with the gateway admin or `docs.litellm.ai` before assuming `claude-sonnet-5` resolves as-is; if the gateway rejects the model name, that's the first thing to check.
- To bypass the gateway entirely (e.g. it's down, or for a quick local test with a personal key), set `LITELLM_BASE_URL=` (empty) in `.env` — the SDK then calls Anthropic directly.
- Endpoint shape: `<base_url>/v1/messages` is appended by the SDK automatically — don't add `/v1/messages` to `LITELLM_BASE_URL` yourself. Reference: [LiteLLM supported endpoints](https://docs.litellm.ai/docs/supported_endpoints), [Anthropic passthrough](https://docs.litellm.ai/docs/pass_through/anthropic_completion).

## Run tests

```bash
python -m pytest -q
```

22 tests, all passing as of 2026-09-04: deterministic red-flag checks (date overlaps, gaps, AI-generated-text heuristic — including a regression test for the em-dash/date-range false-positive fixed in D-18), card rendering, vacancy fetch (mocked HTTP: JSON-LD success, 404, missing-structured-data cases), small-talk short-circuit (D-20), combined-message splitting (D-22).

See `tests/manual_cases/README.md` for 5 self-sourced real-vacancy + synthetic-resume pairs to run through the live bot as a smoke test while Anton's own 5 real cases are still pending.

## What's NOT tested yet

- `screening.py` (the actual Anthropic API call) has no automated test — it needs a real `ANTHROPIC_API_KEY` and costs real tokens per call. Manually verify end-to-end via the bot itself before the demo.
- No test uses the client's real resume/vacancy pairs — Anton still owes 5 real cases (see `communications/2026-09-04-kickoff-followup.md` item 7). Add them to `tests/` as the real acceptance set once they arrive, per the eval methodology in `../.memory-bank/tech-details/stack.md`.
- Resume file parsing (`resume_extract.py`) is untested against a real PDF/DOCX — only the plain-text path is exercised end-to-end so far.

## Architecture

See `../.memory-bank/tech-details/stack.md` for the full rationale. Short version: a managed pipeline (parse vacancy → extract resume → deterministic checks → LLM screening via forced tool-use → render card), not a freely-exploring agent. Deterministic checks (date overlaps, AI-generated-text lexical heuristic) run in plain code and are merged into the LLM's output unconditionally, so a code-provable finding can never be silently dropped by the model.
