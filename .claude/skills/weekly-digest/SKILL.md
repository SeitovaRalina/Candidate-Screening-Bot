<!-- @harness-owned: true; harness-version: 1.0.0 -->
<!-- @spec:REQ-WEEKLY-DIGEST -->
---
name: weekly-digest
description: Write a short, human, anti-slop weekly update of what shipped in the harness repo, for a PUBLIC audience channel. Use as a weekly routine or "harness weekly update", "what shipped this week", "дайджест недели".
cadence: weekly
allowed-tools: [Bash, Read]
---

# /weekly-digest — public "what shipped this week"

Audience-facing, NOT a maintenance report. Motivate colleagues to come, test, discuss. Short and human.

## Steps
1. Gather the week: `git log --since="7 days ago" --oneline`, merged PRs (`gh pr list --state merged --search "merged:>=<date>"`), new/changed skills+hooks (diff of `.claude/skills` `.claude/hooks` `modules`), new decisions (`git log -p .assistant/decisions.md --since="7 days ago" | grep '^+## D-'`).
2. Write the digest — **apply /anti-ai-slop-writing** (no em-dash spam, no puff words, no rule-of-three, no "in today's", concrete verbs, take a position). **Style: human changelog** — a colleague who does NOT know the harness internals must understand every line. Fixed sections, one line per bullet, no connective prose paragraphs. Structure:
   - Title with a **date RANGE**, not "week of": `Effective Harness — апдейт за <start>–<end> <month> <year>` (start = end − 7 days, e.g. `14–21 июля 2026`).
   - **`Что сделали`** (2-4 bullets): each bullet = what shipped + why it matters, one clause. Lead with the thing, not a verb-phrase.
   - **`Что попробовать`** (1-3 bullets): a skill/gate/mode a colleague can test now, each with the exact command in `code` and a plain "what you get".
   - **`Учти`** (0-2): a decision or default worth knowing (one line each).
   - No closing sign-off line. End on the last bullet — no "ping me if it breaks", no call-to-action tail.
   - Total ≤10 content lines. Bullets only under each header — no paragraphs. If nothing shipped, write one honest line, not filler.
   - **Explain, don't name-drop.** Never post a harness-internal term raw. Gloss it in plain words the first time it appears, or replace it outright. Examples: `core` → "ядро (ставится в любой проект)"; `SDD` → "сначала требования, потом код"; `EARS` → "человекочитаемые требования" (never post the word "EARS"); `deterministic CI` → "автотесты на хуки и скрипты"; `stochastic` → "плавающие LLM-проверки"; `/drift` → "бот раз в неделю вычитывает память проекта и спеки"; `module-provenance` → "обновление модуля больше не затирает твои правки". A raw undefined term (SDD / EARS / core / stochastic / provenance / gate name with no gloss) is a slop failure — rewrite it.
   - **Don't conflate the two adoption commands.** `/setup` INSTALLS the harness into a project (file copy + interview). `/onboard` covers an EXISTING project's code with specs (reverse-spec) — it does NOT install anything. When describing `/onboard`, say "восстанавливает спеки из существующего кода", never "заведёт/поставит harness".
3. Post to the PUBLIC channel (e.g. `effective_harness_updates`). Keep it copy-pasteable Markdown.

## Rules
- **Language: Russian.** The audience is Russian-speaking colleagues. This is the one deliberate exception to
  the repo's English-only rule — that rule governs FILES in the repo; this is a chat message, not a file. Keep
  technical terms, commands, paths, and identifiers in English (`/elicit`, `spec-gate`, `AGENTS.md`, PR titles):
  translate the prose, never the code.
- Human, concrete, no AI-slop (this is the flagship — slop here is the worst place for it).
- No internal noise (no PR-review chatter, no drift/coverage numbers — those are the internal channel).
- Highlight what a colleague can TEST, not just what changed.

## Contract
Distinct from `/drift`, the internal maintenance routine that reports to the private `prj_effective_harness`
channel. This one is the public product update. The two are the only live routines (see
`.memory-bank/tech-details/routines.md`).
