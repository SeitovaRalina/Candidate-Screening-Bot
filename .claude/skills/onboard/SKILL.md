<!-- @harness-owned: true; harness-version: 1.0.0 -->
<!-- @spec:REQ-ONBOARD -->
---
name: onboard
description: Bring an existing (brownfield) project under the harness — study the code, docs, and history, build the project map, and reverse-spec capabilities from what already exists. Use when adopting the harness on an existing codebase, "onboard this project", "reverse-spec", "перенести проект на харнес", "описать существующий код".
allowed-tools: [Read, Grep, Glob, Bash, AskUserQuestion, Write]
---

# /onboard — bring an existing project under the harness

Two parts: a cheap **project-map pass** (once), then **incremental reverse-spec** of capabilities.
Never trust auto-generated specs as truth — the agent proposes hypotheses, the human confirms
(observe → source → hypothesis → decide → verify). Specs record CURRENT behavior, not wishes.

## When NOT to use
Greenfield feature (that is `/elicit`); a project already fully onboarded (specs exist, coverage tracked).

## Part A — project-map pass (once)

1. **Study** the repo: structure (dirs, entrypoints), docs (README, AGENTS.md, CLAUDE.md, wiki), and
   history (`git log`, high-churn files). Do NOT read every file — sample entrypoints + the churn hotspots.
2. **Rank by churn** (what changes most → spec first): `git log --format='' --name-only | sort | uniq -c | sort -rn | head -40`.
3. **Write the map** into the memory bank: `.memory-bank/product-overview/` (what it does) + `.memory-bank/tech-details/` (stack, conventions) + a **capability inventory** `.assistant/capabilities.md` — a table of capabilities with `coverage: none|spec|spec+test` per row (all start `none`).
4. **Interview** (`AskUserQuestion`, batched) only for gaps the code cannot answer: intent, non-obvious constraints, what is deliberately unusual. Fold answers in.

Output: a project map + a capability inventory. No behavioral specs yet. Coverage = 0.

## Part B — reverse-spec a capability (incremental, on-touch)

When you first touch capability X (a bug fix, feature, or refactor there):

1. **Read** X's code + its tests (tests are the executable spec — extract acceptance criteria from them).
2. **Draft** `.assistant/specs/<cap>.spec.md` from what the code + tests actually do — EARS requirements
   (`When … the system shall …`), Given/When/Then from existing tests, `id: REQ-<CAP>`. Mark every
   uncertain inference `[NEEDS CLARIFICATION: <hypothesis>]` with a confidence note.
2. **Confirm with the human** (`AskUserQuestion`): present the risky hypotheses; the human accepts, corrects, or rejects. AI output is a hypothesis list, never final requirements.
3. **Anchor**: add `@spec:REQ-<CAP>` comments in the implementing files (trace-gate reads these).
4. **Set** `status: approved` once no `[NEEDS CLARIFICATION]` remains; update `.assistant/capabilities.md` row to `coverage: spec`.

Now capability X behaves like greenfield: further changes flow through the normal pipeline
(spec-gate → /pre-feature → /implementor → /spec-review). Everything not yet reverse-specced stays
advisory — the harness nudges, it does not block edits to unspecced legacy.

## Full self-onboard (the harness itself)
For a bounded, flagship repo (the harness), Part B may be run over ALL kept capabilities at once —
"the harness developed by the harness." For unbounded external legacy, stay incremental (spec-on-touch);
never reverse-spec code you are not about to change.

## Priority
Reverse-spec highest-churn + highest-risk capabilities first (from Part A step 2). Skip stable,
rarely-touched code until it is touched.

## Output contract
`.memory-bank/**` map + `.assistant/capabilities.md` (coverage table) + `.assistant/specs/<cap>.spec.md`
per reverse-specced capability, each with EARS requirements, `status: approved`, and `@spec:` anchors in code.
