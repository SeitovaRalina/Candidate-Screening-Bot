<!-- @harness-owned: true; harness-version: 1.0.0 -->
<!-- @spec:REQ-SPEC-REVIEW -->
---
name: spec-review
description: Review the current code changes in a SEPARATE context and record a verdict the review-gate can read. Use when the user asks to "review", "review my changes", "spec review", "проверь изменения", or when review-gate blocked "done" asking for a review.
allowed-tools: [Bash, Read, Grep, Glob, Task]
---

# /spec-review — separate-context code review → verdict artifact

Reviews the session's uncommitted changes and writes `.claude/.last-review.md`, the artifact
`review-gate.sh` requires before "done" in production mode. The review MUST run in a **separate
context** (a fresh subagent that did NOT write the code). A **different model / provider is
recommended, not forced** — self-review is unreliable (Panickssery NeurIPS'24), but forcing a
second vendor is a cost decision (CP-B). If a cross-provider setup exists (`evals/models.tiers.json`
+ the `llm.effective.land` gateway, D-030), route the reviewer to the opposite provider.

## When NOT to use
No code changes this session (nothing to review); pure docs/plan review (that is the `reviewer`
agent's plan-gate role, before implementation).

## Steps

0. **Intent diff first (review intent before code).** If a spec changed this session, show its diff —
   `git diff HEAD -- .assistant/specs/ .assistant/component-specs/` — and state what requirements were
   ADDED / MODIFIED / REMOVED. Review the *change in intent* before the code diff: does the code diff
   match the intent diff, nothing more, nothing less? A code change with no matching intent change is a
   red flag (scope creep); an intent change with no code change is an unimplemented requirement.

1. **Collect the diff.** `git diff HEAD` (and `git status`). If empty, stop — nothing to review.
   Compute the review sha: `git diff HEAD | shasum | cut -c1-12`.

2. **Spawn the reviewer in a separate context** via the `Task` tool (`subagent_type: reviewer`,
   or a general agent). Pass ONLY: the diff, `.assistant/INVARIANTS.md`, the active spec
   (`.assistant/specs/<slug>.md` or `.assistant/component-specs/*.md`), and the test output —
   never your own reasoning. Prefer a different provider/model where the gateway allows.
   Instruct the reviewer to be adversarial: assume each change is wrong and try to refute it
   before clearing it. Ask for findings as `[SEVERITY] file:line — problem. fix.` plus a final
   `VERDICT: CLEAN` or `VERDICT: ISSUES_FOUND`.

3. **Write the artifact** `.claude/.last-review.md` verbatim in this shape (review-gate parses it):
   ```
   verdict: CLEAN            # or ISSUES_FOUND
   reviewed_sha: <the sha from step 1>
   reviewer: <model/provider used>
   findings: <count>
   ```
   Followed by the full findings list below the header.

4. **Report** the verdict + findings to the user. If `ISSUES_FOUND`, list the fixes; do NOT
   mark the work done — review-gate will (in hard mode) block until a re-review is CLEAN on the
   current sha.

## Contract with review-gate
`review-gate.sh` (REQ-REVIEW-GATE) blocks "done" in hard mode unless `.claude/.last-review.md`
has `verdict: CLEAN` and `reviewed_sha` equal to the current `git diff HEAD | shasum` prefix.
Re-run this skill after any further edit — a stale sha re-blocks.
