# Candidate Screening Bot

Telegram bot that screens a candidate resume against a vacancy before a technical interview and produces a candidate card (verdict, green/red flags with evidence, recommended interview questions). Client: Anton (Effective client). Discovery kickoff: 2026-09-04.

PROJECT_TYPE: 1 (MVP / pre-sale prototype — see `.memory-bank/steerings/project-types.md` copied from harness for the Type 1 vs 2 definition).

## Entry points

- Working agreement: `AGENTS.md`
- Hard rules: `.assistant/INVARIANTS.md`
- Project knowledge: `.memory-bank/index.md`
- Working memory (open questions, decisions): `.assistant/`
- Client communications (sent messages, kept for scope-dispute reference): `communications/`

## Deviation from harness default stack

The playbook's default channel/runtime is Hermes (Effective's internal messaging-gateway product). This prototype does not have Hermes infra available in the build environment and is time-boxed to a same-day demo, so it uses a plain Python Telegram bot (`python-telegram-bot`) + Anthropic API directly instead — see `.memory-bank/tech-details/stack.md` for the full rationale. Revisit for the production handoff.

## Harness install note

Installed by hand (not via the `/setup` skill's interactive flow, to save time under a hard deadline) from a **non-git harness checkout** — `harness_source` in `.harness-lock` is therefore a local marker, not a pinned remote+sha per the harness's own convention. Fix once the harness checkout itself is a git repo with a remote.
