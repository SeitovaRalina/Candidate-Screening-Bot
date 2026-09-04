<!-- @harness-owned: true; harness-version: 1.0.0 -->
---
<!-- @spec:REQ-SYNC -->
name: sync
description: Update an existing Effective Harness install in a target project to the current harness checkout's commit. Pair to /setup — setup installs from scratch, sync updates in-place with drift detection. Use when a project already has .harness-lock and the harness checkout is ahead of the SHA it records.
---

# Skill: /sync

Update an existing Effective Harness install in a target project to the current harness checkout's commit. Pair to `/setup`: setup installs from scratch, sync updates in-place with drift detection.

This skill IS the orchestrator. It runs from the harness checkout, reads the target project's `.harness-lock`, diffs the file tree, and applies harness-owned changes only.

## When to invoke

- Target project has `.harness-lock` (already installed).
- Harness checkout HEAD is ahead of the SHA in `.harness-lock`.
- User wants the new agents / skills / hooks / invariants without rewriting their own memory bank.

If `.harness-lock` is missing → tell the user to run `/setup` instead.

## Invocation

```
/sync [<target-project-path>] [<optional note for the decisions log>]
```

- `<target-project-path>` — absolute path to the target. If omitted, the skill asks.
- `<optional note>` — short reason for this sync, recorded in `.assistant/decisions.md`. Optional.

## Ownership model (the contract)

`.harness-lock` records every managed file with an `owner` field:

| Owner              | Semantics                                                                                                | Sync behavior                                                                                                                |
|--------------------|----------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------|
| `harness`          | Framework file. Source of truth = harness checkout. Examples: `.claude/agents/*`, `.claude/hooks/*`, `.claude/lib/*` (vendored AST detector — `acorn.js`, `walk.js`, `tier-scan.js`; see `.claude/lib/VENDOR.md`), `.claude/skills/*` (skill bodies, not project edits), `.assistant/INVARIANTS.md`, `AGENTS.md`. | Auto-overwrite when upstream changed AND target hash equals lock hash (no drift). Conflict if both changed. |
| `project-template` | Seeded once from harness, then owned by the project. Examples: `.memory-bank/**`, `.assistant/decisions.md`, `.assistant/open-questions.md`, `CLAUDE.md`, `.harness-lock` itself (generated). | Never overwritten. If upstream template changed, surface a one-line diff hint; user merges manually if they want. |
| `project`          | Pure project content created post-install. Lock doesn't track these.                                       | Never touched.                                                                                                              |

Rules:
- A file appears in lock iff it was created by the harness (either `harness` or `project-template`).
- `/sync` never reads or writes files outside the lock's keyspace plus newly added harness-owned paths discovered in the harness checkout.

## Orchestrator workflow

### Step 1 — Verify we are running inside a harness checkout

Same checks as `/setup` Step 1:
- `AGENTS.md`, `.assistant/INVARIANTS.md`, `.claude/agents/` (≥10 files), `.claude/skills/sync/SKILL.md` all present.
- If missing → abort: "Run /sync from the root of a harness checkout."

Record:
- `HARNESS_NEW_SHA = git -C <harness-root> rev-parse HEAD`
- `HARNESS_REMOTE = git -C <harness-root> remote get-url origin`
- Working tree status: if `git -C <harness-root> status --porcelain` returns anything, warn: "Harness checkout has uncommitted changes. Sync will reflect your local edits, not the published commit. Continue?" Wait for explicit y/n.

### Step 2 — Resolve target path

If no target was given, ask. Validate: absolute, exists, directory, not the harness checkout itself, is a git repo (warn if not).

### Step 3 — Read and validate `.harness-lock`

- `<target>/.harness-lock` must exist. If missing → "No harness install detected. Use /setup."
- Parse as JSON. Bail with the parse error if invalid; tell the user to fix manually.
- Extract: `harness_version` (= `HARNESS_OLD_SHA`), `harness_source`, `project_type`, `primary_stack`, `touch_policy`, `files`.

Compare SHAs:
- `HARNESS_OLD_SHA == HARNESS_NEW_SHA` → "Already at `<sha>`. No-op." Exit 0.
- `HARNESS_OLD_SHA` not reachable from `HARNESS_NEW_SHA` (i.e., `git -C <harness-root> merge-base --is-ancestor <old> <new>` fails) → warn: "Lock SHA `<old>` is not an ancestor of harness HEAD `<new>` — harness history was rewritten or you're on a divergent branch. Continue at your own risk?" Wait for explicit y/n.

Compare remotes:
- Lock's `harness_source` host/path ≠ `HARNESS_REMOTE` host/path → ask: "Lock recorded source = `<lock-source>`. Current harness remote = `<HARNESS_REMOTE>`. Switching upstream — confirm?" Wait for y/n.

### Step 4 — Target git hygiene

Run `git -C <target> status --porcelain`. If any tracked file under managed paths (paths in lock + `.claude/` + `.assistant/` + `.memory-bank/`) is dirty → list them, ask: "Target has uncommitted changes in harness-managed paths. /sync writes to those paths. Stash / commit first, then re-run, OR continue and accept overwrites?" Wait.

Current branch: if it's the default branch (`main` / `master` / `trunk`) → suggest `git checkout -b harness-sync-<short-new-sha>` before applying. Don't auto-create; just print the suggestion and proceed if user confirms.

### Step 4.5 — Offer newly available target-runtime layers (D-053)

This is the only mechanism that reaches a project installed before `.omp/` existed — Step 6.6 only runs
during `/setup`, and plain discovery (Step 5's source 3) only picks up `.omp/` for a project already
carrying a `targets[]` key or an existing `.omp/`-prefixed `files{}` entry, so an install that predates
D-053 has neither and would otherwise never be offered the layer at all.

If the lock has **no `targets` key at all** (not even `targets: []`) — the signal that this project was
never asked, as opposed to `targets: []` meaning it was asked and said no — and `<target>/.omp/` does not
already exist: ask via `AskUserQuestion`, same wording and default as `/setup` Step 4 question 6: "This
project's harness install predates the `.omp` (Oh My Pi) target-runtime layer (D-053). Install it now for
this project's `omp`/Oh My Pi developers?" Default **no**.

- **No** → write `targets: []` into the plan (recorded at Step 8's lock regeneration either way, drift or
  not) so this question is asked once, not on every future sync.
- **Yes** → set `targets: ["omp"]` for this run. Step 5's discovery source 3 then treats `.omp/*` exactly
  as it would for a lock that already had `"omp"` in `targets[]` — every `.omp/` file is a new upstream
  path, classified `add`, same file list and owner labels as `/setup` Step 6.6.

If the lock already has a `targets` key — `[]`, `["omp"]`, or otherwise — skip this step: the project was
already asked, either at `/setup` time or by a prior run of this step, and its answer is recorded.

### Step 5 — Build the plan

For each path `p`:

**5a. Harness-owned paths (lock says `harness`, or newly discovered per the five sources below).**

Discovery is not a scan of the core managed roots alone. On the real `design-machine` sync (lock SHA
`6ea46b4d` → HEAD `0dc3d3dc`, install predating the D-042 core/modules split) two more sources turned up
files a core-roots scan cannot see. First, a file added upstream inside an already-installed module is
invisible there, because its upstream path is `modules/<m>/…` while its installed path is `.claude/…` —
six files (`modules/apple/skills/pixel-parity/SKILL.md`, `modules/maintenance/skills/reflect/routine.md`,
three under `modules/mobile-qa/skills/{app-security,load-test,parity-check}/`) had to be found by hand.
Second, two harness-owned data files sit outside every managed root entirely and were never planned at
all: `.assistant/routing.tiers.json` (read by `inject-state.sh`) and `.assistant/lint-registry.json`
(read by `lint-gate.sh`) — both hooks silently degraded (`inject-state.sh` printed no routing table,
`lint-gate.sh` no-opped) with no signal that anything was missing.

Discovery therefore walks five sources:
1. Core managed roots (`.claude/agents/`, `.claude/hooks/`, `.claude/skills/`, `.claude/lib/`,
   `.claude/terse/`, `AGENTS.md`, `.assistant/INVARIANTS.md`).
2. Every `modules/<m>/` tree for each module recorded in `modules[]`, mapping `modules/<m>/<suffix>` to
   its installed path: `skills|agents|hooks|lib|terse/<...>` → `.claude/<suffix>`; `seed/.memory-bank/<...>`
   → `.memory-bank/<...>`. Exception: `modules/<m>/routing.md` is not an installed file — it is appended
   into `CLAUDE.md` — so exclude it from this mapping.

   `modules[]` is not always there to iterate. The `design-machine` lock predates D-042 and has no
   `modules[]` key at all — its top-level keys are `files`, `harness_source`, `harness_version`,
   `install_method`, `installed_at`, `notes`, `primary_stack`, `project_type`, `sync_history`, nothing
   else — so a scan that only iterates `modules[]` enumerates the empty set on exactly the lock that
   produced this bug, and the same six module files go missing again. When `modules[]` is absent, infer
   the installed module set before running discovery: reverse-map the lock's existing `files{}` keys
   onto `modules/*/<suffix>` paths in the harness checkout — an installed path that resolves to some
   `modules/<m>/<suffix>` implies module `<m>` is installed. Match by **path suffix**, not basename —
   basename is ambiguous (`modules/` currently has five files named `routing.md` and duplicate
   `SKILL.md`, `ios.md`, `stack.md`, `swiftui-architect.md`, `apple-ci-engineer.md` across modules; only
   the suffix after `modules/<m>/` is unique, verified zero collisions except `routing.md`, which is
   already excluded from the mapping above). Every module inferred this way is treated as if it had been
   listed in `modules[]`, both for this discovery step and for the `owner: module:<m>` labels written
   back in Step 8's lock regeneration.

   This inference is mandatory, not best-effort — the "1.0 update mechanism" section below already
   states the consequence for the sibling case: a module file whose upstream is unresolved reads as
   `harness_sha = MISSING`, and the 5a action table then prescribes **delete**. On the real run this
   class covered 40 files (26 `module-overwrite` + 14 `module-noop`). A suffix-blind, `modules[]`-only
   scan on a pre-D-042 lock would have wiped every installed module file while the sync reported
   success.

3. Target-runtime layers recorded in `targets[]` (D-053), mapping each named target `<t>`'s root 1:1 onto
   the target project — `.omp/` → `.omp/`, no path-flatten, unlike modules. Today the only defined target
   is `omp`: every file under it — `.omp/agents/*.md`, `.omp/extensions/*.ts`, `.omp/RULES.md`,
   `.omp/APPEND_SYSTEM.md`, `.omp/AGENTS.md` — carries `owner: target:omp`. `.omp/AGENTS.md` is not a
   `project-template` exception: its content is static, generic wrapper prose (an `@`-import of the
   target's own `CLAUDE.md`/`AGENTS.md`/`INVARIANTS.md`, plus a couple of paragraphs of framing text) —
   byte-identical across every install, nothing project-specific to seed once and hand off. It stays
   `target:omp` precisely so a future upstream fix to that wrapper text reaches already-installed projects
   through the normal `harness`/`target:*` auto-overwrite path instead of being stranded as a
   never-applied "template update hint" the way `project-template` would strand it.
   `targets[]` uses the identical missing-key inference as `modules[]` in source 2 above: an older lock
   with no `targets[]` key but with an existing `.omp/`-prefixed `files{}` entry infers `omp` membership.
   A lock with neither a `targets[]` key nor any `.omp/` entry predates D-053 entirely and is handled by
   Step 4.5 above (offer to opt in), not silently skipped here. `.omp/` stays opt-in either way: it is a
   TS hook-bridge plus 14 ported agents that matter only to a project whose developers actually run `omp`,
   not core-`.claude/`-style unconditional content.
4. The harness's own self-test fixtures, `tests/fixtures/workflow/<f>`, mapped to
   `.claude/lib/self-test-fixtures/workflow/<f>` in the target — source path differs from installed path,
   so each entry carries `upstream: tests/fixtures/workflow/<f>`, the same convention a module entry uses.
   `owner: harness`, unconditional (every target needs a working `tier-scan.js --self-test`, not just ones
   with modules or `omp` selected). Installed under `.claude/lib/` rather than at this repo's own
   `tests/fixtures/workflow` path because the target's root `tests/` directory is the project's own — see
   `.claude/skills/setup/SKILL.md` Step 6 for the collision this avoids. This checkout itself does NOT
   also need a `.claude/lib/self-test-fixtures/` directory: with the resolution rule above generalized to
   any `upstream`-carrying entry, `/sync` (and `/setup`) read the source straight from
   `tests/fixtures/workflow/<f>` — the only place these fixtures live in the harness repo. A second copy
   at `.claude/lib/self-test-fixtures/` in this checkout would be dead, unread files.
5. The harness-owned `.assistant/` data files hooks read directly: `.assistant/routing.tiers.json`,
   `.assistant/lint-registry.json`.

A file present in any of these five sources and absent from the target is classified `add`, same as any
other newly-added harness-owned path.

**Do not extend this to `.assistant/component-specs/` or `.assistant/specs/`.** Those hold the *project's*
own specs; the harness checkout's copies describe harness components, not the target's. `spec-gate.sh`
and `trace-gate.sh` fail open when these are absent — the correct state for a fresh consuming project —
so discovery must not start copying them in.

Compute:
- `harness_sha = sha256(<harness-root>/p)` (or `MISSING` if upstream deleted it)
- `target_sha  = sha256(<target>/p)` (or `MISSING` if target doesn't have it)
- `lock_sha    = lock.files[p].sha256` (or `MISSING` if newly added in upstream)

Classify:

| harness_sha | target_sha | lock_sha    | Action                  |
|-------------|------------|-------------|-------------------------|
| ≠ lock      | == lock    | present     | **overwrite** (auto)    |
| ≠ lock      | ≠ lock     | present     | **conflict** (both changed; ask) |
| MISSING     | == lock    | present     | **delete** (auto, with one batch confirm) |
| MISSING     | ≠ lock     | present     | **conflict-delete** (target diverged; ask keep or delete) |
| MISSING     | MISSING    | present     | clean-lock-entry (already gone) |
| present     | MISSING    | present     | **restore** (auto; user removed harness file) |
| present     | any        | MISSING     | **add** (auto; new in upstream) |
| == lock     | == lock    | present     | no-op                   |
| == lock     | ≠ lock     | present     | drift-warn (target edited; upstream didn't; leave alone, surface in summary) |

**5a-special. `.claude/settings.json` — structural merge, not whole-file (REQ-WORKFLOW-TIER WFT-18e).**

`.claude/settings.json` is `owner: harness` but the plain 5a sha-compare treats it as one opaque blob,
and consuming projects routinely drift it — local permissions, `env` entries, extra MCP server config —
none of which is harness content. Under the plain rule, any local edit makes it a **conflict**, and the
batch conflict resolution offers "Keep target for all" as one whole-file choice. A developer who picks
that keeps their local `env`/permissions edits — reasonably — and, invisibly, also keeps whatever hook
registrations their copy happened to have, silently dropping any new harness hook matcher (including
`workflow-tier-gate`'s `PreToolUse` entry on `Workflow`). The result is the gate script lands on disk
with **zero** activation and no signal — a sync that reports success while shipping 0% enforcement.

Do not run `.claude/settings.json` through 5a's whole-file classification. Instead:

1. Parse both the harness's and the target's `settings.json` as JSON.
2. Matcher-level append is not enough — reconcile at the level of individual hook **commands**. Measured
   on the real target: its `settings.json` already declared `matcher: ""` under `PostToolUse`, `Stop`,
   and `UserPromptSubmit`, so a matcher-level append found those matchers already present and skipped
   them — registering only 6 of 12 new hooks. `offload-gate`, `html-slop-gate`, `spec-lint`,
   `test-count-guard`, `trace-gate`, `review-gate` all landed on disk with zero registration and no
   signal — the exact 0%-enforcement failure this section already warns about, reintroduced by the rule
   meant to prevent it. The rule: when an entry with the same `matcher` already exists in the target's
   `hooks.<Event>[]`, append the upstream `command`s that entry declares and the target's `hooks[]` does
   not, deduping by the `command` string. Only when the `matcher` is absent from that event entirely,
   append the whole upstream entry. Never replace or reorder an existing target command.
3. Leave every other top-level key (`env`, `permissions`, MCP config, anything not under `hooks`)
   untouched — those are project-owned by convention even though the file as a whole is lock-tracked.
4. Record the appended entries in the sync summary (Step 11) as
   `+ hooks registered: <script> (<event>/<matcher>)` so the addition is visible, not silent, and
   traceable to a specific command rather than only a matcher.
5. This still updates the file's lock hash to the merged result, not the harness's raw hash — a
   subsequent sync must not treat the target's legitimate local `env`/permissions additions as drift.

This merge runs regardless of whether the target's lock labels `settings.json` `owner: harness` or
`owner: project-template` — older locks (pre-`modules[]` schema) recorded it as `project-template`. The
hooks merge is still required there, and is safe under either label because it is append-only within
`hooks` and never touches `env`/`permissions`.

**Deletions must deregister, not just remove the file.** On the real run, `read-imperative.sh` was
deleted upstream (D-042 cut it) while still registered under `UserPromptSubmit` in the target's
`settings.json` — the plan deleted the script from disk but left a broken hook firing on every prompt,
because nothing in this merge (or in Step 7's apply order) ever removed a deleted script's registration.
When the plan deletes a harness-owned `.claude/hooks/*.sh`, this same merge pass shall remove that
script's `command` entries from `settings.json`, drop any matcher entry whose `hooks[]` becomes empty,
and drop any event whose entry list becomes empty.

**5a-symlink. Dual-CLI installs where a lock-tracked root is a directory symlink (D-053, measured, not
hypothetical).**

On the real `effective-dev-site` sync, the project keeps its skills physically under
`.agents/skills/<name>/…` and symlinks `.claude/skills/<name>` to it, one symlink per skill directory —
so both Claude Code (which only reads `.claude/skills/`) and its other AI-CLI (which reads
`.agents/skills/`) see the same files without duplicating them. Plain 5a classification enumerates
candidate paths under `.claude/skills/` with an ordinary directory walk, and an unqualified `find` does
not descend into a symlinked directory — it reports the symlink itself and stops. Every file physically
living past that symlink boundary is therefore invisible to the walk and reads as `target_sha = MISSING`
even though the file is real, unchanged, and perfectly reachable by any tool that opens the path directly
(`open(2)` — and therefore `sha256sum`, `cat`, `cp` — follows a symlinked directory component
transparently; only *enumeration* breaks). On the real run this misclassified ~29 unchanged files against
a `present` lock hash, landing them in the delete / conflict-delete rows of the 5a action table, and the
run was hand-skipped rather than risk the batch-delete confirm running over live project files — 89 lock
entries were left untouched as a result.

The rule, not a hand skip:

1. **Detection.** Before building the candidate-path set for a managed root, check whether each top-level
   entry under it is a directory symlink: `[ -L "<target>/<root>/<entry>" ]`. This only applies to roots
   whose top-level entries are themselves directories that could stand in for a physically-elsewhere
   store — measured on `.claude/skills/<name>/` (each skill is a directory). It does NOT apply to
   `.claude/agents/` or `.claude/hooks/`: their top-level entries are individual files
   (`architect.md`, `some-hook.sh`), not directories, so there is no directory-symlink case to detect
   there — an individual file that happens to be a symlink is already enumerated correctly by a plain
   `find` with no special handling, per item 2 below. Scope this check to `.claude/skills/` unless a
   future measured case shows another root needs it.
2. **Enumeration.** Any `find` used to discover new upstream paths MUST pass `-L` (follow symlinks) so a
   symlinked root's contents are visible. `sha256sum` / `test -e` / `cat` already follow symlinks by
   default and need no change. (A plain, non-`-L` `find` already lists a symlinked *file* correctly — it
   only fails to descend into a symlinked *directory* — which is why item 1 above doesn't extend to
   `.claude/agents/`/`.claude/hooks/`.)
3. **Hashing and classification — two entry types, matching what `effective-dev-site`'s lock already
   does.**
   - **The symlinked root itself** (`.claude/skills/<name>`) gets its own `files{}` entry, keyed by that
     virtual path, carrying `owner` and `symlink` (see item 4) and **no `sha256`** — there is no file
     content to hash, only a link target to compare. Classify by comparing the live `readlink` output to
     the recorded `symlink` value: match → no-op; a live entry that is no longer a symlink at all, or a
     recorded entry with no live counterpart → **conflict** (ask; this is exactly the destructive
     ambiguity Detection exists to catch — never silently delete a real directory because a symlink was
     expected there, and never silently treat a real directory as safe to walk with `rm -rf`); live
     symlink target differs from the recorded one → **drift** (surface only, per item 4).
   - **Every file physically reachable through the symlinked root** is tracked at its real, physical path
     (e.g. `.agents/skills/<name>/SKILL.md`, not the virtual `.claude/skills/<name>/SKILL.md`) with a
     normal `owner` + `sha256` entry, classified by the ordinary 5a action table exactly as any other
     path — `sha256sum <target>/<real-path>` as usual. This is why Enumeration (item 2) needs `find -L`:
     to discover these real paths starting from the virtual root.
4. **Record the mapping, don't re-detect it every run.** The first sync that detects a symlinked root
   writes the **verbatim `readlink` output** into that root's lock entry as `"symlink": "<value>"` (schema
   in `.claude/skills/setup/SKILL.md` Step 7) — not a canonicalized `realpath`. `readlink` preserves
   whatever the project actually wrote (`effective-dev-site`'s own lock stores relative targets, e.g.
   `../../.agents/skills/<name>`); recording a `realpath`-resolved absolute path instead would disagree
   with that relative value on the very next sync and misreport 19 real, unchanged symlinks as drifted.
   Also set the lock's top-level `"layout": "dual-cli"` field the first time any symlinked root is
   detected (schema in `.claude/skills/setup/SKILL.md` Step 7) — this formalizes the field
   `effective-dev-site`'s own lock had already improvised ad hoc, undocumented, before this rule existed.
   A later sync trusts the recorded `symlink` value first and falls back to live `[ -L ]` detection only
   when it's absent (older lock) or when the live symlink target disagrees with the recorded one — surface
   that as drift; a project relocating its physical skill store is a decision for the user to confirm, not
   silently follow.
5. **Deletion safety — the part the hand-skip was actually protecting against.** Never run a recursive
   delete (`rm -rf`) against a lock-tracked root that is a symlink, or against a path with a symlinked
   ancestor, with a trailing slash — `rm -rf foo/` on a directory symlink descends through it on some `rm`
   implementations and deletes the *real* target's contents, not just the link. Deletes and
   prune-on-deselect always remove the individual tracked *file* paths (through the symlink — safe, this
   only ever unlinks one regular file at its real location) and, only once a formerly-harness-owned
   directory both (a) has zero tracked files left in it and (b) is not itself the symlink root, remove that
   now-empty *physical* directory with a plain `rmdir` — fails safely, refuses on a non-empty directory and
   refuses on a symlink, never `rm -rf`. That `rmdir` only ever targets the physical backing directory
   (e.g. `.agents/skills/<name>/`); it never targets the symlink itself, and must not be relied on to clean
   up the symlink — `rmdir` refuses on a symlink by design, so once the physical directory it pointed at is
   gone, the virtual root (e.g. `.claude/skills/<name>`) is left as a **dangling symlink** unless removed
   separately. Once the physical directory's `rmdir` succeeds (or was never needed because the entry
   itself never had files), remove the now-dangling symlink with a plain `unlink <target>/<virtual-root>`
   (or `rm` with no `-r`/`-f`, i.e. "remove this one link," never "remove this tree") and drop both the
   symlink root's own `files{}` entry and the physical files' entries from the lock.

This applies to any lock-tracked root, not only `.claude/skills/`: the effective-dev-site case is the
measured instance, the rule is general because nothing about directory-symlink enumeration is specific to
skills. Item 1's scoping to `.claude/skills/` is about where the *check* runs today, not a claim that no
other root could ever be symlinked this way — extend it if a future measured case needs it.

**5b. Project-template paths (lock says `project-template`).**

- `upstream_sha = sha256(<harness-root>/p)` (if the upstream template still exists)
- If file removed in upstream → no-op (project owns it now).
- If `upstream_sha == lock.files[p].sha256` → no-op (template didn't change upstream).
- If `upstream_sha ≠ lock.files[p].sha256` → emit a **template-update-hint**: `path → harness updated the seed template. Target file is project-owned; run \`diff <(harness-show p) <target>/p\` to compare.` Do **not** touch the file. Do **not** update the lock's hash for this entry (lock hash records what was seeded, not the current upstream).

**5c. Newly added project-template paths (in upstream, missing in target).**

If the upstream now ships a new `project-template` file (e.g., a new seed under `.memory-bank/` that didn't exist when the project was installed) → seed it with the same logic as `/setup` Step 7, and add the lock entry with `owner: project-template`.

**5d. Detect shadow agents and stale `AGENTS.md` (REQ-WORKFLOW-TIER WFT-65, detect-and-report only).**

This is a measured class, not a hypothetical: consuming projects have been observed running a
project-local `frontend-agent.md` (49 spawns), `backend-agent.md` (40), `test-agent.md` (23) that
shadow the harness's own `frontend`/`backend`/`test` agents — same effective scope, different file,
different `model:`. In one case the project's `backend-agent.md` pins `opus` while the harness's
`backend.md` sits unused pinned `sonnet`, so D-042's biggest declared cost lever never fires there at
all, silently, with nothing in a normal sync run surfacing it.

Read every `<target>/.claude/agents/*.md`, extract each file's declared file-scope (from its frontmatter
or its "Scope" section, however the project documents it) and its `model:` frontmatter value. Group
files whose scopes overlap or are equivalent. Where a group has more than one file **and** the group's
`model:` values differ, flag it as a shadow-agent pair: `<file A> (model: X) shadows <file B> (model: Y)
over scope <description>`.

Separately, compare `<target>/AGENTS.md`'s recorded provenance (lock hash, or a content diff against
the harness checkout's `AGENTS.md` if no hash is recorded) against the harness checkout. If it differs
beyond what `/sync`'s own planned overwrite would apply — i.e. the target's `AGENTS.md` has drifted from
what a clean sync would produce — flag it as stale.

**Ownership boundary, stated explicitly:** this step only detects and reports; it does not resolve
anything. Per `.memory-bank/tech-details/routines.md`, remediating memory-bank/spec/root-doc drift
(including a stale `AGENTS.md`) belongs to `/drift`'s weekly whole-repo audit, not to `/sync`. `/sync`
surfaces the shadow-agent and stale-`AGENTS.md` findings in its plan output (below) precisely because it
already has the target's agent files and lock in hand mid-sync — cheap to detect here — but leaves
merging or renaming files, or rewriting `AGENTS.md`, to the user or to `/drift`.

### Step 6 — Show the plan, collect conflict decisions

Print to user:

```
Sync plan: <HARNESS_OLD_SHA[:8]> → <HARNESS_NEW_SHA[:8]>  (<N> commits)

Auto (no conflicts):
  + add:       <count> files
  ~ overwrite: <count> files
  - delete:    <count> files
  ↻ restore:   <count> files

Templates updated upstream (not touched — yours to merge):
  <list of project-template files where upstream changed>

Local drift on harness files (you edited, upstream didn't — left alone):
  <list>

Shadow agents detected (same scope, different model — not touched, report only):
  <agent A> (model: <X>) shadows <agent B> (model: <Y>) over <scope>
  ...  [or: "none detected"]

AGENTS.md: <"up to date" | "stale — drifted from harness checkout; remediation owned by /drift, not /sync">

Conflicts (both you and upstream changed — need decision):
  <count> files
    <path>
    <path>
    ...
```

**Conflict resolution.**

- 0 conflicts → skip ahead.
- 1 conflict → ask with `AskUserQuestion` (4 options): `Keep target / Use upstream / View diff and decide later (abort sync) / Skip this file`.
- 2..N conflicts → batch decision with `AskUserQuestion`:
  - "Resolve all `<N>` conflicts the same way?"
  - Options: `Use upstream for all` / `Keep target for all` / `Write conflict report and abort` (writes `<target>/.harness-sync-conflicts.md` with file paths + a 3-way diff hint, user resolves manually, re-runs `/sync`).

No per-file mixed decisions in one run — re-run after manual edits if you need granularity. (Keeps the skill simple and predictable; manual cherry-pick is one `cp` away.)

**Final confirmation:**

```
Proceed?  (y / n / show-diff <path>)
```

`show-diff <path>` prints `git -C <harness-root> show <HARNESS_NEW_SHA>:<p>` next to the target file, then re-asks.

### Step 7 — Apply

Order:
1. Adds (new harness files, new project-template seeds).
2. Overwrites (auto + conflict-resolved upstream).
3. Restores.
4. Deletes (with one final "delete N files" confirm).
5. `.claude/settings.json` structural merge (5a-special above): append new hook commands, and remove the
   `command` entries for any script deleted in step 4. This must run *after* deletes, not before or in
   parallel — the deregistration set is only known once the deletes have actually happened. Running it
   earlier is how `read-imperative.sh` stayed registered after being deleted on the real sync.
6. Make all `.sh` under `.claude/hooks/` executable (`chmod +x`).
7. Propagate `.claude/lib/*` (vendored `acorn.js`, `walk.js`, `tier-scan.js`) with the standard harness-owned add/overwrite logic above — no chmod needed, they run via `node <path>`, never directly. Without this step a target that gets `workflow-tier-gate.sh` but not its detector fails open silently (WFT-16) on every Workflow invocation.
8. Ensure the harness ignore block in `<target>/.gitignore` — **identical procedure to `/setup` Step 7.5, read it there** (managed entry: `.claude/sessions/`; `git check-ignore` test, append-only, never negate). A sync must run this too, not only a fresh install: projects installed before this step existed have no such rule, and their `.claude/sessions/` is already accumulating untracked churn. `.gitignore` stays project-owned — it is never added to `.harness-lock`'s `files{}`, so nothing here can overwrite or delete a project's own ignore rules.

Use `cp` / `rm` via `Bash`, not Edit/Write (faster, cleaner logs). Never touch paths outside the lock's keyspace plus the newly-added harness-managed paths.

### Step 8 — Regenerate `.harness-lock`

Preserve from old lock: `installed_at`, `project_type`, `primary_stack`, `touch_policy`.

Update:
- `harness_version` = `HARNESS_NEW_SHA`
- `harness_source` = `<HARNESS_REMOTE>@<HARNESS_NEW_SHA>` (remote URL pinned to commit, never a local path — same rule as `/setup` Step 7)
- `last_synced_at` = ISO 8601 UTC now
- `files` = recompute for every harness-owned + project-template path (use the file's current sha256 in the target)
- `sync_history` = append `{ from: <OLD_SHA>, to: <NEW_SHA>, at: <iso>, conflicts: <count>, decisions: <"keep-target" | "use-upstream" | "none"> }`, cap at last 10 entries

Write atomically: write to `.harness-lock.tmp`, then `mv` over `.harness-lock`.

### Step 9 — Append decision entry

Add to `<target>/.assistant/decisions.md` (next D-NNN, auto-numbered):

```markdown
## D-NNN — Harness synced

**Date:** <YYYY-MM-DD>
**Status:** accepted
**Decision:** Harness updated `<OLD_SHA[:8]>` → `<NEW_SHA[:8]>`.
**Counts:** +<add> ~<overwrite> -<delete> ↻<restore>; <conflicts> conflicts resolved (<keep-target | use-upstream>).
**Template updates pending manual merge:** <list-or-"none">
**Note:** <user-supplied note or omit line>
**Source:** `<HARNESS_REMOTE>@<NEW_SHA>`
```

### Step 10 — Verify

Same sanity checks as `/setup` Step 8:
- `.claude/hooks/inject-state.sh` exists and is executable.
- `.harness-lock` parses as JSON; required keys present.
- `.assistant/INVARIANTS.md` non-empty.
- `AGENTS.md` non-empty.
- SessionStart hook smoke test: `bash <target>/.claude/hooks/inject-state.sh` exits 0.

Plus, when `.claude/lib/tier-scan.js` is present in the sync plan (workflow-tier-gate.sh shipped or
updated) — REQ-WORKFLOW-TIER WFT-18e:
- If `node` is on PATH: `node <target>/.claude/lib/tier-scan.js --self-test <target>/.claude/lib/self-test-fixtures/workflow` exits 0 (mirrors the harness's own `make test-lib`). If `node` is absent, warn that the gate will fail open (WFT-16) in this target rather than silently pass the check. The fixture dir is `.claude/lib/self-test-fixtures/workflow` — discovery source 4 above ships it there precisely so this check has a real fixture dir to run against in every target, not just the harness's own checkout (D-053).
- **Registration assertion (the load-bearing one — do not skip):** `jq -e '.hooks.PreToolUse[] | select(.matcher | test("Workflow"))' <target>/.claude/settings.json` exits 0. A target can have the hook file on disk with no matcher wired up at all (see the structural-merge note under Step 7/5a) — that state is **0% enforcement dressed as a successful sync**, and this is the only check that catches it. Failure here is not a soft warning: surface it as a distinct line in the Step 11 summary, not folded into the generic "verify failed" warning.

Plus, when `.omp/extensions/harness-bridge.ts` is present in the sync plan (`.omp/` newly installed via Step 4.5, or already `owner: target:omp` and just updated) — same activation-check requirement as `/setup` Step 6.6: `grep -q '^export default function' <target>/.omp/extensions/harness-bridge.ts` (catches a corrupted copy), plus the best-effort `~/.omp/agent/config.yml` check described there. A copied bridge file with no signal it actually loads under omp is the same "present on disk, zero enforcement" gap the settings.json registration assertion above exists to catch for Claude Code — surface a warning here too, not just at first install.

Plus, unconditionally, a two-way registration check — broader than the single-matcher assertion above,
which only confirms *a* `Workflow` matcher exists. This one catches both directions of the same class of
bug that the deletion-deregistration fix (Step 5a-special / Step 7 item 5) targets: a script deregistered
without being deleted, or deleted without being deregistered. Both commands were run against the real
target and passed after the deregistration fix was applied by hand:

```
jq -r '.hooks[][] | .hooks[].command' "$T/.claude/settings.json" \
  | sed "s|\$CLAUDE_PROJECT_DIR|$T|" | sort -u \
  | while read -r f; do [ -x "$f" ] || echo "MISSING/NOT-EXEC: $f"; done

comm -23 <(ls "$T"/.claude/hooks/*.sh | xargs -n1 basename | sort) \
         <(jq -r '.hooks[][] | .hooks[].command | split("/")|last' "$T/.claude/settings.json" | sort -u)
```

The first line lists any registered command that doesn't resolve to an executable file on disk; the
second lists any `.claude/hooks/*.sh` not registered to at least one event. Either asymmetry is a
distinct Step 11 summary line, never folded into the generic "verify failed" warning.

Failure → warn, don't auto-rollback. The user has a git checkpoint (Step 4 suggested a branch).

### Step 11 — Summary

```
✓ Harness <OLD[:8]> → <NEW[:8]> in <target>

Applied:
  + <N> new files
  ~ <N> updated
  - <N> deleted
  ↻ <N> restored
  <N> conflicts resolved (<decision>)
  .gitignore: appended .claude/sessions/  (omit the line when already ignored)

Templates upstream updated, project-owned — merge manually if you want them:
  <list>

Next steps:
  1. cd <target>
  2. git status                       # review the diff
  3. git diff .harness-lock           # confirm metadata
  4. git commit -m "harness: sync to <NEW[:8]>"
  5. Run /pre-feature on the next real change — confirms new agents/skills work.
```

## Loop guards

- **No `.harness-lock`** → reject; point at `/setup`.
- **Same SHA** → no-op exit.
- **Lock SHA not ancestor of HEAD** → warn, require explicit y/n (history rewrite or divergent branch).
- **Different `harness_source`** → ask before treating it as the same project.
- **Target git dirty in managed paths** → require explicit y/n.
- **Harness checkout dirty** → warn, require explicit y/n.
- **Lock JSON parse error** → abort; tell user to fix manually.
- **Conflict count > 0 and user picked "write report"** → write `.harness-sync-conflicts.md` and exit 0 without applying anything else (atomicity: partial sync is worse than no sync).
- **Step 7 mid-failure** → leave `.harness-lock` untouched (it's the last write). Re-run `/sync` continues cleanly.
- **User declined at Step 6** → no files written, no lock change. Clean abort.

## What this skill does NOT do

- Does not `git fetch` / `git pull` the harness checkout. User controls the harness HEAD.
- Does not push, commit, or open a PR in the target project.
- Does not merge `project-template` upstream changes into the project's current copy. Surfaces the path; user merges manually.
- Does not migrate lock schema. If lock version drifts incompatibly in the future, a separate `/migrate-lock` skill handles it (OQ).
- Does not touch files outside the lock's keyspace + newly added harness-managed paths, with exactly one exception: `.gitignore`, which Step 7 (apply item 7) appends to (append-only, never rewritten, never lock-tracked). The project's own code is untouched.
- Does not install MCP servers, third-party skills, or modify global `~/.claude/` state.
- Does not rename-detect (upstream rename → recorded as delete+add; user re-applies any local edits manually).
- Does not roll back on Step 10 verify failure. Rollback = `git checkout .` on the sync branch.

## Example flows

### Flow A — clean update, no drift

```
$ cd ~/projects/harness
$ git pull
$ claude
> /sync ~/projects/usmint

[skill reads usmint/.harness-lock → 77cdc03]
[harness HEAD = 99a4ae4]
[plan: +5 files (new agents/skills), ~3 files (skill updates), 0 conflicts]
[user confirms]
[apply + lock regen + decision D-007 appended]
[summary]
```

### Flow B — conflict on harness-owned file

User locally edited `.claude/agents/architect.md` in the target. Upstream also changed it.

```
> /sync ~/projects/usmint

[plan shows 1 conflict: .claude/agents/architect.md]
[AskUserQuestion → user picks "Write conflict report and abort"]
[writes ~/projects/usmint/.harness-sync-conflicts.md with diff hint]
[no other files touched, lock untouched]

# user merges manually, removes report, re-runs /sync
```

### Flow C — template updated upstream

Upstream changed `.memory-bank/steerings/project-rules.md` template. Project's copy is project-owned (per ownership model).

```
[plan output includes:]
  Templates updated upstream (not touched):
    .memory-bank/steerings/project-rules.md
       diff: git show 99a4ae4:.memory-bank/steerings/project-rules.md | diff - .memory-bank/steerings/project-rules.md

[apply runs as normal for harness-owned files]
[user decides off-band whether to merge the template change]
```

## Open questions for this skill

- **OQ-SYNC-1:** Should `project-template` upstream changes be surfaced in the decision log too, or only the summary? (Current: summary only; decision log records "templates pending merge: <list>".)
- **OQ-SYNC-2:** Lock schema migration policy when we add new fields (e.g., a future `signature` field). Probably: tolerant read, strict write — `/sync` accepts older lock shapes and rewrites them in the new shape.
- **OQ-SYNC-3:** Should `/sync` ever pull harness upstream itself? Current answer: no, keep concerns separate. User runs `git pull` in the harness checkout when they want.
- **OQ-SYNC-4:** Rename detection (upstream rename → currently delete+add, loses any local edits to the renamed file). Worth adding `git log --follow` heuristic? Defer until the first real-world rename hurts.

## 1.0 update mechanism — .harness-lock (JSON) + 3-way merge (D-043)

`.harness-lock` (JSON, seeded into the consuming project by `/setup`, gitignored in this source repo).
**The canonical schema is defined once, in `/setup` Step 7 — read it there.** Do not maintain a second
copy here; the two drifted apart before (one said `harness_version` was a commit sha, the other a semver).
`/sync` reads: `commit_sha`, `modules[]`, `targets[]`, `layout`, `skip[]`, and
`files{path → {owner, sha256?, upstream?, symlink?}}` (a directory-symlink entry carries `symlink` and
no `sha256`; every other entry carries `sha256` and no `symlink`).

**Any entry carrying `upstream` is path-mapped — resolve it by `upstream`, never by target path.** This is
not scoped to `owner: module:<m>`; it applies to every `files{}` entry that has an `upstream` field,
whatever its `owner`. Two classes carry one today: module files (`modules/apple/agents/x.md` installed at
`.claude/agents/x.md`) and the self-test fixtures (`owner: harness`, `tests/fixtures/workflow/<f>`
installed at `.claude/lib/self-test-fixtures/workflow/<f>` — discovery source 4 above). Resolve every
entry with an `upstream` field through that field before comparing hashes. Skipping this is not a
cosmetic bug: the comparison would instead look for a harness file at the *installed* path — for the
fixtures, `<harness-root>/.claude/lib/self-test-fixtures/workflow/<f>`, which does not exist in this
checkout (the fixtures live only at `tests/fixtures/workflow/<f>` here) — read `harness_sha = MISSING`,
and the action table would prescribe **delete**, then the next sync re-adds them from source 4, an
add/delete loop on every run. Scoping the resolution to `module:<m>` only, as an earlier draft of this
rule did, reproduces the exact bug this paragraph already documents for modules — just for the one other
`owner` that also happens to carry `upstream`.

Per `owner: harness` file, three-way merge (cruft model):
- **base** = harness file @ `commit_sha`; **ours** = file on disk; **theirs** = harness file @ new HEAD.
1. `hash(disk)==hash(base)` (no local drift) → fast-forward overwrite (silent).
2. only consumer changed → keep consumer's; offer to add to `skip[]`.
3. both changed → `git merge-file` 3-way; on conflict write markers + list in the sync report (never silently drop consumer edits).
4. file in `skip[]` → never touched.
5. `owner: project-template` → never overwritten; emit a one-line diff hint only.

**Prune-on-deselect:** a module dropped from `modules[]` → delete the target files whose lock entry carries `owner: module:<name>`, but only where `hash(disk)==hash(base)` (drifted files are reported, not deleted). Then reverse its non-file registrations: the module's `routing.md` block in `CLAUDE.md`, its hook entries in `settings.json`, and its `.memory-bank/<domain>/` seed — report rather than delete a seed the project has edited. Finally drop the module's `files{}` entries and its `modules[]` element.

**Prune-on-target-deselect (D-053):** the same rule, scoped to `targets[]` instead of `modules[]` — a
target dropped from `targets[]` (a project stops running `omp`) deletes files whose lock entry carries
`owner: target:<name>`, gated by the identical `hash(disk)==hash(base)` safety check, then drops that
target's `files{}` entries and its `targets[]` element. This includes `.omp/AGENTS.md` — it is
`owner: target:omp` like the rest of the layer (see discovery source 3 above for why it is not a
`project-template` exception), so dropping `omp` removes it along with everything else under `.omp/`,
subject to the same drift check as any other `target:omp` file.

> Earlier wording said "delete its `modules/<name>/` files". That was unimplementable: `/setup` never copies a `modules/` directory into a consuming project (setup Step 6.5 flattens module content into `.claude/` + `.memory-bank/`), so the path never existed in the target and a deselect silently pruned nothing while reporting success.

**Version safety:** refuse to sync a workspace whose `harness_version` is NEWER than this checkout (bidirectional guard). MAJOR bump (removed INVARIANT id / role / hook event / lock field) → warn + require opt-in; MINOR/PATCH apply per the table above.
