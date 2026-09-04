# Candidate Screening Bot — prototype

Telegram bot: send a vacancy (hh.ru link or pasted text) and a candidate's resume (PDF/DOCX/TXT file, or pasted text) in either order; get back a candidate card (verdict, green/red flags with quotes, interview questions).

This is `prototype/` — the harness's mode-gate sandbox (`.assistant/mode.json` = `prototype`). See `../CLAUDE.md` for the harness install and the Hermes-vs-plain-Python deviation, `../.assistant/decisions.md` for D-1..D-9, `../.assistant/open-questions.md` for what's still pending client confirmation.

## Known limitation — read before demoing

**hh.ru vacancy links do not currently work.** hh.ru closed unauthorized public API access in April 2026 (verified live, see D-9). Sending a hh.ru link produces a clear error message; **paste the vacancy text directly instead** — that path is fully implemented and tested.

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

11 tests, all passing as of 2026-09-04: deterministic red-flag checks (date overlaps, gaps, AI-generated-text heuristic), card rendering, vacancy fetch (mocked HTTP, including a regression test for the 403 case above).

## What's NOT tested yet

- `screening.py` (the actual Anthropic API call) has no automated test — it needs a real `ANTHROPIC_API_KEY` and costs real tokens per call. Manually verify end-to-end via the bot itself before the demo.
- No test uses the client's real resume/vacancy pairs — Anton still owes 5 real cases (see `communications/2026-09-04-kickoff-followup.md` item 7). Add them to `tests/` as the real acceptance set once they arrive, per the eval methodology in `../.memory-bank/tech-details/stack.md`.
- Resume file parsing (`resume_extract.py`) is untested against a real PDF/DOCX — only the plain-text path is exercised end-to-end so far.

## Architecture

See `../.memory-bank/tech-details/stack.md` for the full rationale. Short version: a managed pipeline (parse vacancy → extract resume → deterministic checks → LLM screening via forced tool-use → render card), not a freely-exploring agent. Deterministic checks (date overlaps, AI-generated-text lexical heuristic) run in plain code and are merged into the LLM's output unconditionally, so a code-provable finding can never be silently dropped by the model.
