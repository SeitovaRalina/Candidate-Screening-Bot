<!-- @harness-owned: true; harness-version: 1.0.0 -->
---
<!-- @spec:REQ-SETUP -->
name: setup
description: Install Effective Harness into a target project. Orchestrates the file copy, interviews the user about the target project, and seeds the initial memory bank, decisions log, and harness-lock. Run this skill from a harness checkout; pass the target project path. Replaces the manual install prompt in README.md.
---

# Skill: /setup

Install Effective Harness into a target project. This skill IS the orchestrator — it does the work itself, no separate subagents required for the install. Use `/pre-feature` or `/research` later for design work in the target project.

## When to invoke

User just cloned this harness repo (or already has it locally) and wants to install it into another project. They run the AI-CLI inside the harness checkout, then type `/setup` with an optional target path.

## Invocation

```
/setup [<target-project-path>] [<short context, 1–2 sentences>]
```

- `<target-project-path>` — absolute path to the target project root. If omitted, the skill asks.
- `<short context>` — optional one-line description ("an iOS app for gift card scanning"); helps seed the memory bank. If omitted, the skill asks.

## Orchestrator workflow

### Step 1 — Verify we are running inside a harness checkout

The orchestrator checks the current working directory contains:
- `AGENTS.md`
- `.assistant/INVARIANTS.md`
- `.claude/agents/` with ≥10 agent files
- `.claude/skills/setup/SKILL.md` (this file)

If any of these are missing, abort with: "Run /setup from the root of a harness checkout (cloned from github.com/effective-dev-os/harness)."

Record the harness commit SHA: `git -C <harness-root> rev-parse HEAD` (for `.harness-lock`).

### Step 2 — Resolve target path

If no target path was given:
- Ask the user: "Absolute path to the target project (the project the harness will be installed into)?"

Validate the path:
- Must be an absolute path
- Must be a directory that exists
- Must not be the harness checkout itself (abort if equal)
- Should be a git repo (warn if not — harness expects branch workflow per ANTI-3)

### Step 3 — Inspect the target project

Read (best-effort; missing files are fine):
- `README.md`, `CLAUDE.md`, `AGENTS.md` if they exist
- `package.json`, `Cargo.toml`, `pyproject.toml`, `pubspec.yaml`, `Package.swift`, `build.gradle*`, `go.mod` — detect primary language(s)
- `.gitignore`, `.editorconfig` — detect existing conventions
- Top-level dir layout (1 level deep)

Detect:
- Primary language(s) and stack
- Whether `.memory-bank/` / `.assistant/` / `.claude/` already exist (any of these = previous install or conflict)
- Whether `.omp/` already exists (previous partial omp install — Step 4 Q6 defaults "yes" on this)
- Existing `CLAUDE.md` (back up to `CLAUDE.local.md` if it exists and is non-trivial — i.e., not a stub)

### Step 3.5 — Mine prior AI-CLI sessions (parallel)

Before interviewing the user, mine the prior Claude Code / OpenCode / Codex sessions for the target project. They typically contain a lot of user context the user won't think to repeat in the install interview: domain glossary, tech-stack details, friction patterns, recurring complaints, open questions already voiced, validated approaches.

**Detect session directories.** Slugify the target path into the AI-CLI's session-dir convention:

- **Claude Code:** `~/.claude/projects/<slug>/*.jsonl` — slug = target absolute path with `/` replaced by `-` (e.g., `/Users/ayusavin/Projects/jukte` → `-Users-ayusavin-Projects-jukte`).
- **OpenCode:** `~/.opencode/<slug>/...` *(format TBD — Phase 6 research; for now, best-effort search)*
- **Codex:** `~/.codex/<slug>/...` *(format TBD; best-effort search)*

If no session files exist in any of these locations → skip this step, proceed to Step 4 with no extra context.

If ≥3 session files exist → run the MapReduce flow below.

**Map phase: spawn 3 parallel `general-purpose` agents via `Task` tool, single message, 3 Task calls.**

Each agent gets a non-overlapping subset of recent sessions (split by date — agent A = newest third, B = middle third, C = oldest third). Each agent's prompt:

> You are a session-miner for the Effective Harness `/setup` skill. Read the following Claude Code / OpenCode / Codex session JSONL files in `<dir>` (your assigned subset: `<file1>`, `<file2>`, ...). **Do NOT read full files** (they can be 10–100MB) — use `head -300` + `tail -300` + a mid-sample per file. Look for:
>
> - **Tech stack signals** — frameworks, libraries, databases the user has mentioned working with
> - **Domain glossary** — project-specific terms ("portal", "card-balance", "tunnel", etc.) the user uses
> - **Friction signals** — places the user says "no", "нет", "не так", "стоп", "поправь" — quote 1–2 examples
> - **Validation signals** — places the user says "да", "отлично", "идеально", "продолжай" — quote 1–2 examples
> - **Recurring complaints / wishes** — anything the user has asked for repeatedly
> - **Open questions** — design questions the user has voiced but not resolved
> - **Implicit invariants** — rules the user has stated ("don't push to main", "don't mock the DB", "always check logs first")
>
> Output strict YAML per the `researcher` agent schema. Each finding carries `confidence: high | medium | low` and cites the session filename + line range.
> Keep it under 600 words.

**Reduce phase: orchestrator dedupes findings across the three agents.**

Group by category (stack / glossary / friction / validation / complaints / open-questions / invariants). Drop duplicates by `(category, finding-substring)`. Surface the highest-confidence findings.

**Use of findings:**
- Tech-stack signals → propose defaults for the **Primary stack** interview question (user can still override).
- Domain glossary → seed `.memory-bank/tech-details/glossary.md` with the terms.
- Implicit invariants → suggest entries for `.assistant/open-questions.md` as "OQ-INV-1: confirm <invariant> applies project-wide?" (don't auto-add to INVARIANTS.md — they're harness-wide, not project-wide).
- Open questions → seed `.assistant/open-questions.md` with OQ-2..N.
- Friction / validation signals → seed `.memory-bank/steerings/project-rules.md` extended notes.

**Show the user the mined summary** before the interview:

```
Mined N sessions across <date-range>:

Tech stack detected: <list>
Domain terms: <list>
Recurring user invariants: <quoted, with session refs>
Open questions you've voiced: <quoted>

I'll use this to pre-fill the interview defaults below. You can override anything.
```

**Loop guards:**
- Session files >100MB total combined → ask the user before spending the tokens.
- No useful findings (all agents returned empty arrays) → proceed silently to Step 4 without surfacing anything.
- User declines mining (privacy / time) → skip and proceed.

### Step 4 — Interview the user (6 questions max)

Use `AskUserQuestion` (single multi-question call) to collect:

1. **PROJECT_TYPE** — "Type 1 (MVP / pre-sale / experiment)" or "Type 2 (production, human-gated)". See `.memory-bank/steerings/project-types.md`.
2. **Primary stack** (multiSelect) — backend / web frontend / iOS / Android / Flutter / infra. Used to pick executing-agent scope defaults in the target's `CLAUDE.md`.
3. **One-line vision** — "What does this project do, in one sentence?" Seeds `.memory-bank/product-overview/vision.md`.
4. **Touch policy** — should `/setup` overwrite an existing `CLAUDE.md` (back up as `CLAUDE.local.md`) or refuse to overwrite (abort, ask user to merge manually)?
5. **Existing memory bank** — does the project already have `.memory-bank/` (skip seeding) or not (seed templates)?
6. **omp layer** — do this project's developers run `omp` (Oh My Pi) alongside or instead of Claude Code? Default "no" unless the target already has an `.omp/` directory (previous partial install) or the user's Step 3.5 mined sessions mention `omp`/`oh-my-pi`. If yes → Step 6.6 installs `.omp/`. Most consuming projects will answer no; `.omp/` is a 18-file opt-in layer (14 ported agents, a hook-bridge extension, native context files), not core — see D-053.

If the user has skipped clarifying context in Step 2, also ask: "Anything important the harness should know before generating an initial memory bank? (Sensitive dirs to avoid, compliance notes, existing tooling we should respect.)"

Where Step 3.5 mined findings, use them as **pre-filled defaults** in the question options (e.g., the multi-select for Primary stack defaults to the detected stack; the one-line vision is pre-filled with a synthesized summary from session content; the user confirms or edits).

### Step 5 — Plan the copy (dry-run summary)

Before any file is written, print the plan:

```
About to install harness <commit-sha> into <target-path>:

  Will create:
    .claude/agents/                 (12 files)
    .claude/hooks/                   (19 hooks)
    .claude/lib/                     (vendored acorn + acorn-walk, MIT, pinned; tier-scan.js detector — used by workflow-tier-gate.sh and /routing-audit)
    .claude/lib/self-test-fixtures/workflow/  (20 files, copied from this checkout's tests/fixtures/workflow — the fixture dir Step 8's tier-scan.js --self-test needs; installed under .claude/lib/, not at the top-level tests/ path it lives at in this repo, so it never collides with the target's own test suite)
    .claude/skills/                 (15 core skills + selected module skills from interview)
    .claude/settings.json
    .assistant/INVARIANTS.md
    AGENTS.md

  Will create if omp layer selected (Step 6.6, D-053):
    .omp/AGENTS.md                  (seed — imports the target's own CLAUDE.md/AGENTS.md/INVARIANTS.md)
    .omp/RULES.md, .omp/APPEND_SYSTEM.md
    .omp/agents/                    (14 ported agents)
    .omp/extensions/harness-bridge.ts

  Will create if missing (templates):
    .memory-bank/index.md           (seed)
    .memory-bank/product-overview/vision.md  (from your one-line answer)
    .memory-bank/product-overview/anti-stories.md  (copy of harness's, mark as project-template)
    .memory-bank/steerings/project-rules.md  (copy of harness's, mark as project-template)
    .memory-bank/tech-details/stack.md  (skeleton — fill in)
    .assistant/decisions.md         (D-001 = installed from harness)
    .assistant/open-questions.md
    CLAUDE.md                       (short entry point)
    .harness-lock                   (version metadata)

  Will append (never overwrite, never delete existing lines):
    .gitignore                      (+ .claude/sessions/ — harness-managed block)

  Will skip / preserve:
    Any file the project already owns and Touch policy says skip
    Existing CLAUDE.md → backed up to CLAUDE.local.md if Touch policy says overwrite

Proceed? (y / n / details)
```

Wait for explicit user approval. Abort cleanly if user says no.

### Step 6 — Execute the copy

Copy files using `Bash` (cp / rsync, never agent-driven Edit/Write for the bulk copy — that's slower and noisier in logs). Use `cp -R` with explicit source paths. Never copy:
- `.git/`
- `swarm-report/` (harness-specific historical record)
- `.harness-lock` from harness checkout (we generate a fresh one for the target)
- This harness checkout's `.memory-bank/` content (only the *structure* — empty dirs + index.md template)
- Anything matching `.gitignore` patterns the user listed
- **`modules/` — never bulk-copied.** The harness core is `.claude/{agents,skills,hooks,lib}` + `.assistant` + `.memory-bank`. Domain clusters live under `modules/<name>/` and install only on request (Step 6.5). Core never imports a module.
- **`.omp/` — never bulk-copied.** Same reasoning as `modules/`: it's a 18-file opt-in target-runtime layer (Step 6.6), not core. Unconditionally shipping a TS hook-bridge and 14 ported agents to every project — most of which have never run `omp` — is dead weight with no upside.

Do copy `tests/fixtures/workflow/` from this checkout, but not to its own path — remap it to `<target>/.claude/lib/self-test-fixtures/workflow/` (unconditional, `owner: harness`). This is the one core file group whose source path differs from its installed path outside of module remaps; see the rationale in Step 5's dry-run plan and the field notes under Step 7.

### Step 6.5 — Install opt-in modules (D-042)

Ask (multi-select, or infer from Step 3 detected stack): which domain modules does this project need?
Modules: **apple** (SwiftUI/iOS/macOS), **scraping** (anti-bot/proxy/surface), **embedded** (MCU/firmware), **mobile-qa** (parity/app-security/load-test + android/flutter), **web-frontend** (visual-spec, quickstart, visual/anim gates), **maintenance** (reflect/defrag/research/audit/diagnose/refactor).

For each SELECTED module `<m>`:
- **Never overwrite. Check first.** Before every copy, if the destination path already exists → STOP and ask (`keep-existing` / `overwrite` / `skip-this-file`). A bare `cp -R` is how a project silently loses its own `audit`, `research`, `quickstart`, or `refactor` skill — module-vs-project collisions are the realistic case, and last-write-wins gives no signal that it happened.
- `cp modules/<m>/agents/*.md` → `<target>/.claude/agents/` (if any)
- `cp -R modules/<m>/skills/*` → `<target>/.claude/skills/` (if any)
- if the module ships hooks → copy into `<target>/.claude/hooks/` + append registrations to `<target>/.claude/settings.json`. **No module ships a hook today** — keep this step, but do not build for it until one does.
- append the module's `modules/<m>/routing.md` fragment to the target's `CLAUDE.md` "## Modules" section (domain profile-keywords live in the module, not core)
- copy the module's `.memory-bank/<domain>/` seed templates (else the module's agents halt on a missing steering file)
- **Record provenance per file.** Every file copied above gets a `files{}` entry in `.harness-lock` with `"owner": "module:<m>"` and its sha256, and `<m>` is appended to the lock's `modules[]`. This is not bookkeeping for its own sake: after the copy a module file is byte-indistinguishable from a core file, so without the attribution `/sync` cannot map it back to its upstream path and prune-on-deselect has nothing to delete by.

Do NOT install a module the user did not pick — that is the whole point of the split.

**Module agent names are a platform constraint, not a style preference.** Claude Code identifies a subagent **only** by its `name:` frontmatter — the file path is ignored, so nesting under `.claude/agents/<module>/` buys no isolation, and two agents sharing a `name:` collide silently with filesystem read order deciding the winner. (Skills differ: they are identified by their directory name, and a nested one additionally gets a qualified `dir:skill` form.) Therefore every module agent MUST carry a domain-prefixed `name:` — `apple-ci-engineer`, `swiftui-architect`, `embedded-c-reviewer`, `cortex-m-low-level`. That prefix is the only namespace an agent gets.

### Step 6.6 — Install omp layer (opt-in, D-053)

Only if Step 4 question 6 was "yes". `.omp/` is not a domain module (it doesn't live under `modules/`, and it isn't scoped to a stack like `apple` or `embedded`) — it's a target-runtime layer: the native context/rules/agents/hook-bridge that `omp` (Oh My Pi) reads instead of `.claude/`. `omp` reads `.claude/skills/` and `CLAUDE.md` on its own, but it ignores `.claude/agents/` and the hooks wired in `.claude/settings.json` — without this layer the harness runs in an omp session as unenforced prose, the exact 0%-enforcement failure mode D-048 already measured for a different rule.

Same "never overwrite, check first" rule as Step 6.5: if `<target>/.omp/` already exists, stop and ask (`keep-existing` / `overwrite` / `skip-this-file`) before touching anything under it — a hand-rolled `.omp/` predates this skill knowing about `omp` at all in a project that experimented with it early.

- `cp -R .omp/agents/*.md` → `<target>/.omp/agents/` — 14 ported agents, `owner: target:omp` each.
- `cp .omp/extensions/harness-bridge.ts` → `<target>/.omp/extensions/harness-bridge.ts` — `owner: target:omp`. Runs the target's own `.claude/hooks/*.sh` under omp; needs the target's `.claude/settings.json` hook wiring to already be in place, so this step must run after core `.claude/` is copied (Step 6), not before.
- `cp .omp/RULES.md .omp/APPEND_SYSTEM.md` → `<target>/.omp/` — `owner: target:omp`. Static framework prose (omp's sticky-rules and build-style equivalents of `.claude/terse/ruleset.md`); no project customization point.
- `cp .omp/AGENTS.md` → `<target>/.omp/AGENTS.md` — `owner: target:omp`, same as the other four groups. Its content is a static wrapper (an `@`-import of the target project's own `CLAUDE.md` / `AGENTS.md` / `.assistant/INVARIANTS.md` by relative path, plus a couple of framing paragraphs) — byte-identical across every install, nothing per-project to seed once and hand off. It is deliberately NOT `project-template`: that tier would mean an upstream fix to the wrapper text never reaches an already-installed project, and this file has exactly that failure once already (see D-053's fix to its own prose, which described the harness repo itself rather than the installing project).
- Add `"omp"` to the lock's `targets: []` array (new top-level field, sibling to `modules[]` — see Step 7). Record every file above in `files{}` with `owner: target:omp`; none of them need an `upstream` field (source path and installed path are identical — `.omp/<suffix>` in the checkout maps to `.omp/<suffix>` in the target, unlike a module's `modules/<m>/<suffix>` → `.claude/<suffix>` flatten).
- **Activation check for the bridge (the omp analog of the settings.json registration assertion in Step 8).** A copied `harness-bridge.ts` with no signal that omp actually loads it is the same "present on disk, zero enforcement" failure mode as an unregistered hook. Two checks, in order of how much they can actually verify:
  1. Static, always run: `grep -q '^export default function' <target>/.omp/extensions/harness-bridge.ts` — catches a truncated or corrupted copy. This is a weak check (it can't detect "omp never loads this file"), documented as such rather than presented as more than it is.
  2. Best-effort, only when it can say something real: `omp` extensions load either by directory convention (a project's own `.omp/extensions/*.ts`, auto-discovered) or via an explicit path entry in the user's `~/.omp/agent/config.yml`, and which mode a given omp build uses is not something this skill can determine from outside ([omp extension-authoring docs](https://omp.sh/docs/extension-authoring); [DeepWiki: Creating Extensions](https://deepwiki.com/can1357/oh-my-pi/11.1-creating-extensions), both checked 2026-08-25). If `~/.omp/agent/config.yml` exists on the installing machine, grep it for a path referencing `<target>/.omp/extensions` or `harness-bridge.ts`. Present → the bridge is confirmed wired for config-based loading. Absent → warn explicitly: "`~/.omp/agent/config.yml` exists but does not list this project's `.omp/extensions/harness-bridge.ts` — if your omp build requires explicit config.yml registration rather than per-project auto-discovery, add it there; if your build auto-discovers `.omp/extensions/`, ignore this." If `~/.omp/agent/config.yml` doesn't exist at all, say so and stop there — same posture as the `node`-absent branch of the tier-scan check: state what could not be verified rather than silently passing.

Do NOT install `.omp/` when Step 4 question 6 was "no" — that is the whole point of the opt-in, same as modules.

### Step 7 — Seed target-specific files

These are not bulk-copied; they are generated based on the interview answers.

**`<target>/.harness-lock`** (JSON):

`harness_source` MUST be a remote URL pinned to a commit, never a local filesystem path. Canonical form: `<git-remote-url>@<commit-sha>` (e.g. `git@github.com:effective-dev-os/harness.git@abc1234…`). Local checkout paths leak the installer's machine layout and are unreachable from CI / other developers / future installs.

This block is the **canonical `.harness-lock` schema**. `/sync` reads it; it does not define a second one.

```json
{
  "schema": 1,
  "harness_version": "1.0.0",
  "harness_source": "<git-remote-url>@<commit-sha>",
  "commit_sha": "<harness HEAD at install / last sync>",
  "installed_at": "<ISO 8601 UTC>",
  "last_synced_at": "<ISO 8601 UTC, set by /sync>",
  "install_method": "skill:/setup",
  "project_type": <1 or 2>,
  "primary_stack": ["<list from interview>"],
  "touch_policy": "<from the Step 3 interview>",
  "modules": ["apple"],
  "targets": ["omp"],
  "layout": "single-cli",
  "skip": [],
  "files": {
    ".claude/agents/architect.md":        { "owner": "harness",          "sha256": "<computed>" },
    ".claude/hooks/inject-state.sh":      { "owner": "harness",          "sha256": "<computed>" },
    ".claude/agents/apple-ci-engineer.md":{ "owner": "module:apple",     "sha256": "<computed>", "upstream": "modules/apple/agents/apple-ci-engineer.md" },
    ".claude/lib/self-test-fixtures/workflow/clean.js": { "owner": "harness", "sha256": "<computed>", "upstream": "tests/fixtures/workflow/clean.js" },
    ".omp/agents/architect.md":           { "owner": "target:omp",       "sha256": "<computed>" },
    ".omp/AGENTS.md":                     { "owner": "target:omp",       "sha256": "<computed>" },
    ".memory-bank/product-overview/vision.md": { "owner": "project-template", "sha256": "<computed>" },
    "CLAUDE.md":                          { "owner": "project-template", "sha256": "<computed>" },
    ".claude/skills/apple-impl":          { "owner": "harness",          "symlink": "../../.agents/skills/apple-impl" },
    ".agents/skills/apple-impl/SKILL.md": { "owner": "harness",          "sha256": "<computed>" },
    ...
  }
}
```

Field notes that matter:
- `harness_version` is the **semver** of the harness release (`1.0.0`), not a commit sha. The sha lives in `commit_sha` / `harness_source`.
- `owner` is one of `harness` | `project-template` | `module:<name>` | `target:<name>`. A file the project wrote itself is simply absent from `files{}` — that absence is what protects it (`/sync` only touches paths it owns).
- `upstream` is REQUIRED whenever a file's source path in this checkout differs from its installed path in the target — today that's `module:*` entries (`modules/<m>/agents/x.md` → `.claude/agents/x.md`) and the self-test fixtures (`tests/fixtures/workflow/*` → `.claude/lib/self-test-fixtures/workflow/*`). It is NOT needed on `target:*` entries: a target-runtime layer's source path and installed path are identical (`.omp/agents/x.md` → `.omp/agents/x.md`, no flatten), so nothing to record. `.omp/AGENTS.md` is `target:omp` like the rest of `.omp/`, not a `project-template` exception — its content is a static wrapper, byte-identical across installs.
- `targets` (D-053) is the `.omp`-style sibling of `modules`: names of installed target-runtime layers (today only `"omp"` is defined; OpenCode/Codex adapters — `.memory-bank/tech-details/target-runtimes.md` — will add their own elements here once they ship, rather than inventing a second array). Empty by default (`[]`), which means "asked, declined" — distinct from the key being **absent** entirely, which means "never asked" (a lock from before D-053). `/sync` only offers to install `.omp/` for a lock in the latter state — see `.claude/skills/sync/SKILL.md` Step 4.5 — never re-asks a lock that already has `targets: []`.
- `layout` is an optional top-level string: `"dual-cli"` when the project keeps at least one lock-tracked root reachable through a directory symlink to a physically-elsewhere store, for parity with a second AI-CLI (see the `symlink` field below and `.claude/skills/sync/SKILL.md` Step 5a-symlink). Absent, or `"single-cli"`, otherwise.
- A `files{}` entry for a directory that is itself a symlink (not a file inside one — see the `.claude/skills/apple-impl` example above) carries `owner` and `"symlink": "<value>"` and **no `sha256`** — there is no content to hash, only a link target to compare. `<value>` is the **verbatim `readlink` output** (relative if the project wrote it relative, e.g. `../../.agents/skills/apple-impl` — NOT a canonicalized absolute `realpath`, which would disagree with a relative on-disk value on the very next sync and misreport it as drift). Every file physically reachable through that symlink is tracked separately, at its real physical path (e.g. `.agents/skills/apple-impl/SKILL.md`), with an ordinary `owner` + `sha256` entry — same as any other harness-owned file. `/sync` writes the `symlink` entry the first time it detects the symlink and trusts it thereafter — see `.claude/skills/sync/SKILL.md` Step 5a-symlink for why plain directory-walk discovery silently mishandles this layout otherwise, and for the classification rule for both entry types.

**`<target>/.assistant/decisions.md`**:
```markdown
# Decisions Log

> Append-only chronological record. When a decision is overturned, add a new entry with date + reason. Never edit or delete prior entries.

---

## D-001 — Harness installed
**Date:** <YYYY-MM-DD>
**Status:** accepted
**Decision:** Effective Harness installed at commit `<sha>` via the `/setup` skill. `PROJECT_TYPE: <N>`. Primary stack: <list>.
**Source:** `<git-remote-url>@<sha>` (remote URL pinned to commit — never a local filesystem path)
**Touch policy chosen at install:** <overwrite | preserve>
```

**`<target>/.memory-bank/index.md`**: minimal table of contents pointing at the seeded files. Project fills in as work progresses.

**`<target>/.memory-bank/product-overview/vision.md`**: starts with the user's one-line answer; includes prompts for the project owner to expand "Target audience", "DoD", "What we don't do".

**`<target>/.memory-bank/tech-details/stack.md`**: a stub with detected language(s) + dependencies + framework hints from Step 3 inspection plus stack signals from Step 3.5 session mining. Marked TODO for the project owner.

**`<target>/.memory-bank/tech-details/glossary.md`**: seeded from Step 3.5 domain-term findings. Each term carries a one-line definition (best-effort, marked TODO if the agent couldn't infer one). Empty if Step 3.5 found nothing.

**`<target>/.assistant/open-questions.md`**: in addition to the seed OQ-001 about stack lock-in, append OQ-2..N for the open questions the user voiced in prior sessions (from Step 3.5 mining).

**`<target>/CLAUDE.md`**: a short entry point — points at `AGENTS.md`, `.memory-bank/index.md`, declares `PROJECT_TYPE`, declares stack. Backs up any existing `CLAUDE.md` to `CLAUDE.local.md` if Touch policy = overwrite.

**`<target>/.assistant/open-questions.md`**: seed empty file with a header comment ("OQ-001 — set this project's primary stack and tooling versions explicitly").

### Step 7.5 — Ensure the harness ignore block in `<target>/.gitignore`

Claude Code writes per-session state into `<target>/.claude/sessions/`. It is machine-local churn, never
project content, and if it is not ignored it lands in the project's first commit after install — which is
exactly what happens in practice, because nothing else in the flow reminds anyone. Ignoring it is the
skill's job, not the developer's.

Managed entries (this list is the whole contract — do not extend it silently):

```
.claude/sessions/
```

Procedure, for each entry `e`:

1. **Already ignored → do nothing.** Test with `git -C <target> check-ignore -q <e>`; exit 0 means some
   existing rule already covers it (a literal line, or a broader pattern like `.claude/`). Use
   `check-ignore`, not `grep`: a project that already ignores all of `.claude/` needs no second rule, and a
   grep for the literal string would miss that and append a redundant line on every install.
   If `<target>` is not a git repo, fall back to a literal-line grep of `.gitignore`.
2. **Not ignored → append.** Create `.gitignore` if absent. Append (never rewrite the file, never reorder
   or drop existing lines):

```
# Effective Harness (managed) — AI-CLI session state, machine-local
.claude/sessions/
```

   If the block header already exists, add the missing entry under it instead of writing a second block.
3. **Never negate.** If the project has an explicit un-ignore (`!.claude/sessions/`), leave it alone and
   report the conflict in the Step 9 summary — the project's own rule wins.

`.gitignore` is **project-owned**: do not add it to `.harness-lock`'s `files{}`. The harness appends to it
and never claims it, so `/sync` will never overwrite or delete a project's ignore rules.

### Step 8 — Verify install

Run sanity checks on the target dir:
- `.claude/hooks/inject-state.sh` is executable (`chmod +x` if not)
- `.harness-lock` parses as JSON
- `.assistant/INVARIANTS.md` exists and is non-empty
- `AGENTS.md` exists and is non-empty
- The SessionStart hook script runs without error: `bash <target>/.claude/hooks/inject-state.sh` → exit 0
- `node` is on PATH (`node --version`). If absent, warn explicitly: `workflow-tier-gate.sh` will fail
  open (WFT-16) on every Workflow invocation in this project until `node` is installed — this is a
  silent no-op otherwise, so the warning must be printed, not just logged.
- If `node` is present: `node <target>/.claude/lib/tier-scan.js --self-test <target>/.claude/lib/self-test-fixtures/workflow`
  exits 0 (REQ-WORKFLOW-TIER WFT-18e; mirrors the harness's own `make test-lib`). The fixture dir is
  `.claude/lib/self-test-fixtures/workflow`, not `tests/fixtures/workflow` — `/setup` never bulk-copies
  `tests/` into a consuming project (that path is the project's own test suite), so a check pointed at
  `<target>/tests/fixtures/workflow` fails by construction in every install, not because anything is
  broken (D-053). Step 6 copies the fixture dir to its `.claude/lib/` location precisely so this check has
  something real to run against.
- `jq -e '.hooks.PreToolUse[] | select(.matcher | test("Workflow"))' <target>/.claude/settings.json`
  exits 0 — confirms the gate is actually registered, not just present on disk.

Any check fails → emit a warning, don't abort silently.

### Step 9 — Summary and next steps

Output to the user:

```
✓ Harness <commit-sha> installed in <target-path>

Created:
  - 13 agent files under .claude/agents/
  - 16 skills under .claude/skills/ (including /pre-feature, /elicit, /setup)
  - SessionStart hook
  - .memory-bank/ skeleton + vision.md seed
  - .assistant/INVARIANTS.md, decisions.md (D-001), open-questions.md
  - .harness-lock
  - .gitignore: appended .claude/sessions/  (or: already ignored — no change)
  - .omp/ layer installed (omit this line when Step 4 question 6 was "no")

Next steps:
  1. cd <target-path>
  2. Open the project in Claude Code / OpenCode / Codex
  3. Edit .memory-bank/product-overview/vision.md to fill out target audience and DoD
  4. Edit .memory-bank/tech-details/stack.md to lock the stack
  5. Open a PR labeled "harness: initial install"
  6. Run /pre-feature on your first real change to verify the consilium works
```

## Loop guards

- **Already installed.** If `<target>/.harness-lock` exists with same commit SHA → emit "Already installed at this version. Use `/sync` to update."
- **Older harness install.** If `.harness-lock` exists with a different SHA → refuse `/setup`; tell the user to run `/sync` instead (in-place update with drift detection).
- **Half-installed state.** If `.claude/` exists but `.harness-lock` is missing → ask the user to either clean up manually or accept the Touch policy and proceed.
- **Re-run after error.** If Step 6 failed mid-copy, every retry starts by checking `.harness-lock` (if it doesn't exist, copy is incomplete and safe to redo).

## What this skill does NOT do

- Does not push to the target project's git remote.
- Does not commit to the target project. The user opens the PR.
- Does not install MCP servers or third-party skills (out of scope per D-015 — MCP servers stay "Recommended, with documented fallbacks" per `.memory-bank/tech-details/dependencies.md`).
- Does not auto-update later. That's `/sync` — run it from a harness checkout against the target.
- Does not run `/pre-feature` for the first real change. User does that explicitly.
- Does not read full session JSONLs in Step 3.5 — only head/tail/mid samples (files can be 10–100MB).
- Does not store mined session content in the harness repo — findings are summarized and folded into the target project's `.memory-bank/` + `.assistant/`; raw quotes go to `swarm-report/setup-mining-<date>.md` in the target project (gitignored by default).

## Example flows

### Flow A — fresh project

```
$ git clone https://github.com/effective-dev-os/harness
$ cd harness
$ claude
> /setup ~/projects/my-new-app

[skill asks interview questions]
[skill prints plan]
[user confirms]
[copy + seed runs]
[summary printed]

$ cd ~/projects/my-new-app
$ claude
> /pre-feature "add user signup flow"
```

### Flow B — existing project, with existing CLAUDE.md

```
$ cd harness
$ claude
> /setup ~/projects/jukte "Government tax portal for RK; treat as Type 2 production"

[skill detects existing CLAUDE.md]
[asks Touch policy → user picks "back up to CLAUDE.local.md and overwrite"]
[plan + confirm + copy + seed]
[user manually merges any custom rules from CLAUDE.local.md into the new CLAUDE.md afterwards]
```
