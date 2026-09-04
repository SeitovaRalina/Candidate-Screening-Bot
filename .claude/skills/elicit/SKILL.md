<!-- @harness-owned: true; harness-version: 1.0.0 -->
<!-- @spec:REQ-ELICIT -->
---
name: elicit
description: Interview the developer to turn a rough idea into a clean, checkable spec before any code. Use when the user asks to "elicit requirements", "gather requirements", "start a spec", "write a spec", "собрать требования", "написать спеку", or when spec-gate blocked a source edit asking for a spec.
allowed-tools: [AskUserQuestion, Read, Write, Bash]
---

# /elicit — requirements front-door

Turns a rough ask into an approved, checkable spec that `spec-gate` accepts. This is stage 1 of
the pipeline. Output is EARS requirements with explicit open questions — never code.

## When NOT to use
The task is trivial / mechanical (a typo, a one-line fix); prototype mode where the user wants to
skip straight to a throwaway build (spec is optional in prototype — check `.assistant/mode.json`).

## Two capture paths
- **Interview** (default) — the steps below: ask, draft, clarify.
- **Prompt-capture** (lightweight) — when the developer has already described the task in their own
  prompts, parse THEIR words into a first-pass requirement draft instead of a fresh interview. Ground
  every requirement in the developer's actual phrasing + the code they accepted — never invent intent.
  Still confirm before `status: approved` (auto-generated specs that the human never confirms defeat
  the purpose). Use interview only for the gaps prompt-capture leaves open.

## Steps

1. **Read the ask + context.** The rough idea (or the developer's recent prompts, for prompt-capture),
   plus `.assistant/INVARIANTS.md` and any related spec.

2. **Draft first, then clarify** (generate-then-refine). Write a first-pass `requirements.md` in
   **EARS** — every requirement is one of:
   - Ubiquitous: `The <system> shall <response>.`
   - Event: `When <trigger>, the <system> shall <response>.`
   - State: `While <state>, the <system> shall <response>.`
   - Unwanted: `If <adverse trigger>, then the <system> shall <response>.`
   - Optional: `Where <feature>, the <system> shall <response>.`

3. **Ask ≤5 questions in ONE round** (batched, not one-at-a-time) via `AskUserQuestion` — only the
   highest-impact ambiguities, each with 2–3 concrete options. Mark every unresolved point inline
   as `[NEEDS CLARIFICATION: <question>]`. Fold answers into a dated `## Clarifications` log.

4. **Write the spec** to `.assistant/specs/<slug>.md` (slug = branch name, `git rev-parse
   --abbrev-ref HEAD | sed 's|.*/||'`). Header: `id: REQ-<SLUG>` + `status: approved` once all
   `[NEEDS CLARIFICATION]` are resolved (spec-gate blocks source edits while any remain).
   Include acceptance criteria as Given/When/Then so tests can be derived, not fitted.

5. **Stop.** Do not proceed to plan or code — hand off to `/pre-feature`. In production mode
   `spec-gate` enforces this; the `Goal.md` exit condition is: the developer and the spec agree
   on the same task, with zero open `[NEEDS CLARIFICATION]`.

## Output contract
`.assistant/specs/<slug>.md` with EARS requirements, Given/When/Then acceptance criteria,
a `## Clarifications` log, and `status: approved` only when no clarification markers remain.
`spec-lint` will warn on weak wording; `trace-gate` (hard mode) later expects `@spec:REQ-<...>`
anchors in the implementing files.
