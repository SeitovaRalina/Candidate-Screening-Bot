<!-- @harness-owned: true; harness-version: 1.0.0 -->
<!-- @spec:REQ-SPEC-DEFRAG -->
---
name: spec-defrag
cadence: weekly
description: Periodic full audit of spec health — drift, orphans, contradictions, staleness, coverage gaps — and propose fixes as a PR. The spec analog of /memory-bank-defrag. Use weekly or on demand, "spec defrag", "audit specs", "проверить состояние спек".
allowed-tools: [Bash, Read, Grep, Glob, Task]
---

# /spec-defrag — periodic spec-health audit (propose-only)

The drift answer: instead of blocking on drift every Stop (noisy), run a deep audit on a cadence
(weekly cron, reusing the defrag workflow) and PROPOSE fixes. Propose-only — a human approves the PR.

## Checks
1. **Coverage / UNBOUND** — run `/spec-coverage`. Approved requirements with no `@spec:` anchor.
2. **ORPHAN** — `@spec:REQ-x` anchors whose requirement no longer exists (full sweep; `trace-gate`
   only catches the touched slice at Stop).
3. **DRIFT** — for each anchored requirement, compare the spec's last-changed date to the anchored
   file's churn (`git log -1 --format=%ct`). A requirement whose code changed much more recently
   than its spec is a drift candidate — list it, do not auto-rewrite.
4. **CONTRADICTION / DUPLICATION** — spawn a reviewer (`Task`, separate context) to read the spec set
   and flag overlapping or conflicting requirements across specs (the main brownfield pain). Judgment,
   not a grep.
5. **STALE** — specs not touched in N days while their code churned.
6. **COVERAGE-GAP** — high-churn tracked files with NO spec (from git churn ranking) — the reverse-spec
   backlog for `/onboard`, prioritized.

## Output
A `swarm-report/spec-defrag-<date>.md` report: per-check findings + a prioritized fix list. Then draft
a PR with the mechanical fixes (remove orphan anchors, flag drift for human review). NEVER auto-rewrite
a requirement — AI proposes, human decides. Intent coverage numbers from `/spec-coverage` head the report.

## Cadence
Weekly via the defrag cron (same machinery as `/memory-bank-defrag`). On-demand any time.
