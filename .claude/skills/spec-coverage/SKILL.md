<!-- @harness-owned: true; harness-version: 1.0.0 -->
<!-- @spec:REQ-SPEC-COVERAGE -->
---
name: spec-coverage
cadence: weekly
description: Report which declared requirements have code anchors and tests — the read side of trace-gate. Intent coverage, not line coverage. Use for "spec coverage", "what's specced", "intent coverage", "покрытие спеками".
allowed-tools: [Bash, Read]
---

# /spec-coverage — intent coverage report

Answers "which approved requirements are actually satisfied?" — the read side of `trace-gate`.
This is INTENT coverage (are the declared requirements anchored + tested), not code-line coverage.

## Steps
1. Run `bash ${CLAUDE_SKILL_DIR}/scripts/coverage.sh`. It lists every approved requirement with
   ANCHORED (a `@spec:REQ-x` exists in tracked code) and TESTED (a test references it), then a
   ratio over DECLARED requirements — never over the whole codebase (repo-wide % demoralizes on
   brownfield; the denominator is intent, not lines).
2. Read the output. Flag: UNBOUND (approved, not anchored) — these are gaps `trace-gate` blocks in
   hard mode; and anchored-but-untested requirements — candidates for a characterization test.
3. For a brownfield migration, cross-reference with `.assistant/capabilities.md` (coverage=none rows)
   and prioritize reverse-speccing the highest-churn unspecced capabilities first.

## Output
A coverage table + a one-line ratio. No repo-wide percentage. Use as a health signal + a to-do list
for `/onboard` (reverse-spec the gaps) and `/spec-defrag` (fix drift).
