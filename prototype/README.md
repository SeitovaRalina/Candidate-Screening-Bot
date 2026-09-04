# Candidate Screening Bot — prototype

Telegram bot: send a vacancy (hh.ru link or pasted text) and a candidate's resume (PDF/DOCX/TXT file, or pasted text) in either order; get back a candidate card (verdict, green/red flags with quotes, interview questions).

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

## Run tests

```bash
python -m pytest -q
```

12 tests, all passing as of 2026-09-04: deterministic red-flag checks (date overlaps, gaps, AI-generated-text heuristic), card rendering, vacancy fetch (mocked HTTP: JSON-LD success, 404, missing-structured-data cases).

## What's NOT tested yet

- `screening.py` (the actual Anthropic API call) has no automated test — it needs a real `ANTHROPIC_API_KEY` and costs real tokens per call. Manually verify end-to-end via the bot itself before the demo.
- No test uses the client's real resume/vacancy pairs — Anton still owes 5 real cases (see `communications/2026-09-04-kickoff-followup.md` item 7). Add them to `tests/` as the real acceptance set once they arrive, per the eval methodology in `../.memory-bank/tech-details/stack.md`.
- Resume file parsing (`resume_extract.py`) is untested against a real PDF/DOCX — only the plain-text path is exercised end-to-end so far.

## Architecture

See `../.memory-bank/tech-details/stack.md` for the full rationale. Short version: a managed pipeline (parse vacancy → extract resume → deterministic checks → LLM screening via forced tool-use → render card), not a freely-exploring agent. Deterministic checks (date overlaps, AI-generated-text lexical heuristic) run in plain code and are merged into the LLM's output unconditionally, so a code-provable finding can never be silently dropped by the model.
