<!-- @harness-owned: true; harness-version: 1.0.0 -->
<!-- @spec:REQ-DRIFT -->
---
name: drift
cadence: weekly
description: One weekly whole-repo drift audit — the unified successor to /memory-bank-defrag + /spec-defrag. Fans out claim-checking subagents over the ENTIRE repo (memory bank, specs, root docs) against a deterministic ground-truth snapshot plus 2026 web facts, adversarially verifies each finding, and opens ONE propose-only PR. Use weekly, on demand, "drift check", "полная дефрагментация", "проверить дрифт всего".
allowed-tools: [Bash, Read, Grep, Glob, Task, WebSearch]
---

# /drift — whole-repo drift audit (propose-only, multi-agent)

Replaces the two narrow defrags with one deep weekly pass. The lesson that created it: a delta-driven
defrag folds only *recent* changes and never re-audits files no commit touched — so a stale count
("13 skills"), a ghost agent (`product-owner`), a fiction table (crons that never shipped), and a
routine that doesn't exist (`/reflect`) all survived for weeks. The fix is **audit every claim against
ground truth, every run, over the whole repo** — not narrate the diff.

Propose-only: AI finds and drafts, a human approves the PR. Never auto-merge, never push to main.

## Non-negotiables

- **Count, don't narrate.** Every quantitative or named claim is diffed against the Step-0 snapshot, not
  taken on trust. A count that matches "feels right" is not verified — it's unchecked.
- **Shipped ≠ aspirational.** Classify each claim before judging it. A claim in present tense asserting
  current state is SHIPPED and MUST match the snapshot. A claim under `planned` / `Phase ≥ current` /
  `roadmap` / `deferred` / `OQ-` / `draft` is ASPIRATIONAL and is **exempt from filesystem verification** —
  a "planned cron" naming a nonexistent workflow is correct, not drift. Never rewrite an aspirational item
  into present tense; when a roadmap item actually ships (its files now appear in the snapshot), MOVE it to
  current-state, don't duplicate it.
- **External claims need a source.** Any statement about the outside world (tool versions, competitors,
  provider capabilities) carries a confidence flag + a 2026 web source, or it is dropped.
- **Verify before you assert.** A subagent's finding is intent, not fact. Adversarially re-check each fix
  before applying (Step 4). If a claim can't be confirmed against the repo or the web, leave it and flag it.
- **Fold, don't lose.** Collapse patch-on-patch to current state; a reversal that carries decision-relevant
  context stays as a one-line supersession note. That's history, not a patch.
- **No process noise.** The docs record the *project*, not this maintenance. No "actualized on <date>" trails.
- **Propose-only.** Edits land on a `drift/<date>` branch → PR. Never commit to main, never auto-merge.

## Workflow

### Step 0 — Ground-truth snapshot (cheap, deterministic, every run)

```bash
.claude/skills/drift/scripts/ground-truth.sh
```

Emits the authoritative inventory at HEAD: agents/skills/hooks/modules (+per-module agents/skills/seed/
routing/specs), workflows, VERSION, mode, last decisions, declared REQs vs `@spec:` anchors (UNBOUND/ORPHAN,
core + installed modules), and the routines.md CLAIMS. This snapshot is the run's source of truth — it is
NOT delta-scoped, so drift in files no recent commit touched is still caught.

**Routines blind spot:** live Claude routines are in the cloud dashboard, not git. The script can only print
what `routines.md` claims. Treat every routine claim as UNVERIFIED and surface it for the human to confirm
against the dashboard — this is the exact hole that let `/reflect` + `/audit` be documented as live routines.

### Step 1 — Fan out claim-checkers (parallel `Task`, one per area)

Spawn subagents in parallel, each owning a slice and each handed the Step-0 snapshot verbatim. Areas:
`product-overview/*`, `tech-details/*`, `steerings/* + index.md`, root docs (`README.md`, `AGENTS.md`,
`CLAUDE.md`, `CHANGELOG.md`), specs (`.assistant/component-specs/*` + `modules/*/component-specs/*`), and an
EXTERNAL-web slice (`dependencies.md`, `existing-solutions.md`, `litellm-gateway.md` — uses WebSearch).

**No-internet degradation:** headless/cron routine runs may lack MCP search (`mcp-omnisearch`/Tavily) and
sometimes all web. Order of preference: MCP search → built-in `WebSearch` → if neither is available, SKIP the
external-doc slice entirely and record "external slice skipped (no web)" in the report. Never fabricate an
external fact to fill the gap — the internal audit (Steps 0–2, the bulk) runs fine offline.

Each returns a strict drift table, one row per claim:
`file:line | claim (quote) | reality (verified; +source/date/confidence for external) | verdict | fix`
verdict ∈ `CURRENT | STALE | FICTION | ASPIRATIONAL-AS-REAL`. Every SHIPPED claim is diffed against the
snapshot; PHANTOM = a name asserted as existing but absent from the snapshot (catches ghost agents);
UNDOCUMENTED = a snapshot entry no doc mentions.

### Step 2 — Inventory cross-check (mechanical, from the snapshot)

Regex the whole memory bank for `\d+ (agents|skills|hooks|modules|workflows|routines)` and assert each
equals the snapshot; every agent/skill/hook/module/workflow name mentioned as existing must be in the
snapshot. Emit mismatches as a table the human sees: `claim | doc says | filesystem says | verdict`.

### Step 3 — Adversarial verify (parallel `Task`)

For each proposed fix, a second subagent tries to REFUTE it: is the "reality" actually true, is the claim
really SHIPPED (not aspirational), does the web source hold, would the edit introduce a NEW wrong fact?
Drop or downgrade any fix that doesn't survive. External claims without a live 2026 source are dropped.

### Step 4 — Synthesize + apply (surgical)

Build the master drift table (severity-ranked). Apply surgical edits to the stale lines only — preserve each
file's voice/headings/structure; never regenerate a whole file; English only; no slop; `TODO(verify)` rather
than a guess. Fold spec fixes: remove genuine ORPHAN anchors, flag DRIFT for human review, never auto-rewrite
a requirement. Leave ASPIRATIONAL items in future tense under their labeled section.

### Step 5 — Verify (re-run the snapshot)

Re-run `ground-truth.sh` and re-assert every count/name claim now matches — catches a fix that corrected one
file but not its twin (the classic index-says-14 / CLAUDE-says-13 split). Then `git grep` for leftovers of
anything retired.

### Step 6 — One PR (propose-only)

Branch `drift/<YYYY-MM-DD>`. Write `swarm-report/drift-<date>.md` (the master table + the routines-to-confirm
list + external facts that moved). Open ONE PR; NEVER push to main, NEVER auto-merge. Post 1-2 lines to
Mattermost per the two-channel policy in `routines.md` (internal channel; report-only unless a PR opened).

## Supersedes

This skill is the intended single replacement for `/memory-bank-defrag` (whole memory bank) and `/spec-defrag`
(spec health) — both are folded in (Step 1 specs slice + Step 0 UNBOUND/ORPHAN). Once `/drift` is proven,
retire those two skills and collapse their two routines into one weekly `/drift` routine. Until then `/drift`
can run alongside them on demand.
