<!-- @harness-owned: true; harness-version: 1.0.0 -->
---
<!-- @spec:REQ-CONTRIBUTE -->
name: contribute
description: Propose a new agent or skill to the Effective Harness source of truth via a fork-based PR. Checks/installs gh, syncs the contributor's private fork with upstream, scaffolds the agent/skill with valid frontmatter, self-checks against INVARIANTS, and opens a PR into effective-dev-os/harness:main. Use when an engineer wants to upstream a reusable agent/skill (e.g. a Jetpack-Compose Android subagent) during a hackathon or normal work.
---

# Skill: /contribute

Full-automation contribution flow for the **fork → PR** model. The harness source of truth is **private** (`effective-dev-os/harness`). Contributors get **read** access, hold a **private fork**, and propose changes via pull request. They never push to upstream `main` (INVARIANT §10).

**When to invoke:** an engineer built (or wants to build) a reusable agent or skill and wants it merged upstream into the harness.

**When NOT to invoke:**
- Editing the harness for yourself only, no upstream intent → just edit your local files.
- Proposing a non-trivial *design* change (new pipeline stage, invariant change) → run `/pre-feature` first, then `/contribute` the result.
- Bugfix to an existing agent/skill → still fine here; pick "edit existing" in Step 4.

## Invocation

```
/contribute
```

Optional argument: `agent <name>` or `skill <name>` to skip the first prompt.

## Hard rules this skill enforces (refuse, don't work around)

- **§2** — skill/agent name is task-based, kebab-case, **no project prefix**. Reject `harness-*`, `<projectname>-*`. If the engineer insists, abort with the §2 quote.
- **§10** — never push to `main`, never `--force`, never `--no-verify`. Always a `propose/<name>` branch → PR.
- **§12** — scan scaffolded content for secrets (API keys, tokens, real internal URLs/IPs). Abort if found.
- **§3** — if the new agent emits findings, its output schema must match the universal YAML in INVARIANTS §3.
- License — repo is proprietary (`LICENSE`, Effective, LLC). Do not add OSS license headers or relicense.

## Orchestrator workflow

### Step 1 — Preconditions: `gh` installed + authed

1. `gh --version` → if missing:
   - macOS: `brew install gh`
   - Debian/Ubuntu: `sudo apt install gh` (or the official apt repo if not packaged)
2. `gh auth status` → if not logged in, this is **interactive**, cannot be automated. Surface to the user:
   > Run `! gh auth login` (GitHub.com → HTTPS → login with browser), then re-run `/contribute`.
   Stop here until authed.

### Step 2 — Resolve the harness fork

Upstream is fixed: `effective-dev-os/harness`.

1. Detect current location. If CWD is already a clone whose `git remote get-url upstream` (or `origin`) points at `effective-dev-os/harness` or the user's fork → use it.
2. Else check for the user's fork: `gh repo view <user>/harness`.
   - No fork → `gh repo fork effective-dev-os/harness --clone --remote` (creates a **private** fork — forks of a private repo are private; never public). This sets `origin` = fork, `upstream` = `effective-dev-os/harness`.
   - Fork exists but not cloned locally → `gh repo clone <user>/harness` then add upstream remote.
3. Confirm remotes: `origin` = `<user>/harness`, `upstream` = `effective-dev-os/harness`. Fix if wrong.

### Step 3 — Sync fork with upstream

```
git fetch upstream
git checkout main
git merge --ff-only upstream/main   # never rewrite; if non-ff, abort and tell user to resolve
git push origin main
```

If `--ff-only` fails (fork main diverged), do **not** force. Surface: "fork main diverged from upstream — reconcile manually." Stop.

### Step 4 — Gather the proposal

Ask (AskUserQuestion or inline) — skip what was passed as args:
- **Type:** new agent | new skill | new process/playbook | edit existing agent/skill
  - A **process/playbook** is a skill whose body is a captured mini-process (pure prose workflow, no subagent fan-out) — the mechanism by which an engineer teaches the agent fleet "how we do X". Scaffold it at `.claude/skills/<name>/SKILL.md` with the same frontmatter (`name`, `description`) as any skill; all existing gates (§2 naming, §10 no-push-to-main, §12 secret scan, self-check) apply unchanged.
- **Name:** kebab-case, validate against §2. Re-prompt on violation.
- For an **agent:** role/purpose (one line), file scope it executes on (e.g. `**/*.kt`), `model` (default `opus` for review roles, `sonnet` for narrow exec — match siblings), `tools` list.
- For a **skill:** one-line description, trigger phrases, whether it's an orchestrator (spawns subagents) or a single-pass tool.

### Step 5 — Scaffold the file

Branch first: `git checkout -b propose/<name>`.

**Agent** → `.claude/agents/<name>.md`:
```
<!-- @harness-owned: true; harness-version: 0.0.1 -->
---
name: <name>
description: <one line — role + file scope>
model: <opus|sonnet>
tools: [Read, Edit, Write, Grep, Glob, Bash, WebSearch, WebFetch]
---

# <Name>

## Mission
<what it does>

## What to read first
1. ...

## Output format
<code + summary, OR strict YAML per INVARIANTS §3 if it emits findings>

## Escalation
- <when to hand off to another role>

## Anti-patterns
- ...
```
Keep the `@harness-owned` marker — `/sync` uses it for drift/ownership tracking.

**Skill** → `.claude/skills/<name>/SKILL.md`: frontmatter (`name`, `description`) + body matching the house style (see `pre-feature/SKILL.md` for an orchestrator, `quickstart/SKILL.md` for a single-pass tool). Include When-to-invoke / When-NOT, Invocation, and the workflow.

Fill real content from Step 4 — do not leave `TODO` stubs unless the engineer explicitly wants a Phase-3 placeholder (some shipped agents legitimately carry `## TODO Phase 3`).

### Step 6 — Self-check (block PR on failure)

Run these gates; report pass/fail per item:
1. **§2 naming** — kebab-case, no project prefix.
2. **Frontmatter valid** — required keys present, YAML parses.
3. **§3 schema** — if agent emits findings, the schema matches.
4. **§12 secrets** — grep the new file for key/token patterns, internal URLs, IPs. Abort on hit.
5. **No collision** — `<name>` not already taken in `.claude/agents/` or `.claude/skills/`.
6. **Routing** — if a new keyword→role row belongs in root `CLAUDE.md` "Profile keywords → roles", add it in the same branch.

### Step 7 — Commit, push, open PR

```
git add .claude/agents/<name>.md   # or skills/<name>/, + CLAUDE.md if routing changed
git commit -m "feat(agents|skills): add <name> — <one line>"
git push -u origin propose/<name>
gh pr create \
  --repo effective-dev-os/harness \
  --base main \
  --head <user>:propose/<name> \
  --title "feat: add <name>" \
  --body-file <generated from .github/pull_request_template.md, checklist filled>
```

No `Co-Authored-By` trailer (project convention).

### Step 8 — Surface to user

Output: PR URL + a one-line summary of the self-check results. Done. Maintainer reviews and merges upstream.

## Loop guards

- §2 violation in name → re-prompt **once**; second violation → abort with the §2 quote.
- Non-ff fork sync → abort, never force.
- Secret detected → abort, do not commit.
- Name collision → abort, suggest "edit existing" path instead.

## What this skill does NOT do

- Does not merge the PR (maintainer gate).
- Does not push to upstream `main` or any upstream branch (§10).
- Does not relicense or add OSS headers — repo is proprietary.
- Does not run the consilium — for design-level proposals, run `/pre-feature` first.
