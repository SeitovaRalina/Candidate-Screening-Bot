<!-- @harness-owned: true; harness-version: 1.0.0 -->
---
name: lint-setup
description: Add a per-file linter for a language the change-triggered lint hook (lint-gate.sh) flagged as unconfigured. Web-searches the canonical fast linter/formatter for an extension, confirms + installs it via brew/npm/pip, writes its config plus a row into .assistant/lint-registry.json so the hook runs it on the next edit, then offers to upstream the default via /contribute. Use when lint-gate emits "no linter configured for '.<ext>'. Run /lint-setup", when a .lintsetup marker exists, or when the user asks to add/configure a linter for a language.
---
<!-- @spec:REQ-LINT-SETUP -->

# Skill: /lint-setup

Interactive companion to `.claude/hooks/lint-gate.sh`. The hook is **non-interactive**: on an edit to a file whose extension has no entry in `.assistant/lint-registry.json`, it emits one `LINT-WARN: no linter configured for '.<ext>'. Run /lint-setup` line and appends the extension to `.claude/sessions/<session_id>.lintsetup`. **This skill owns all interaction** — finding, confirming, installing, and registering a linter.

Nothing here edits `lint-gate.sh`. The registry file is the sole extension point: add a row and the deterministic hook picks it up on the next `Edit|Write|MultiEdit`.

## Inputs

- Explicit extension: `/lint-setup .zig`.
- No arg → read the flagged extensions from `.claude/sessions/*.lintsetup` (deduped). If several, ask which to set up first via `AskUserQuestion`.
- No arg and no marker → ask the user which language/extension they want to configure.

## Flow

### 1. Identify the extension

Normalize to a leading-dot form (`.zig`, `.ex`, `.lua`). If read from a `.lintsetup` marker, list what the hook saw this session and let the user pick.

### 2. Recommend a linter (verify, don't guess)

`WebSearch` the canonical **fast, single-file** linter or formatter for that language — the kind that runs sub-second on one file (the hook's budget), not a whole-repo suite. Prefer the community-standard tool. Present **1-2 options**, each with:

- tool name + one line on what it checks,
- the install command (`brew install …` / `npm i -g …` / `pip install …`),
- the single-file invocation, using the `{file}` placeholder the registry expects (e.g. `ruff check {file}`, `zig fmt --check {file}`).

Re-verify recommendations that may be stale (tool renamed, deprecated) rather than trusting memory.

### 3. Confirm + install (RISKY — always confirm)

Installing a package manager tool is a risky action per the working agreement. Use `AskUserQuestion` to confirm the exact install command before running it. Never auto-install unattended. Install via the local package manager only (`brew` / `npm` / `pip`); never write tokens or fetch from ad-hoc URLs (§12).

If the user declines install, still offer to write the registry row: the hook checks `command -v` and skips a linter whose binary is absent, so the row stays inert until the tool is installed.

### 4. Write config + registry row

1. If the linter needs a project config file (e.g. `.ruff.toml`, `.eslintrc`), create it with a minimal sane default — ask before overwriting an existing one.
2. Add / update the extension's row in `.assistant/lint-registry.json` (create the file from the shipped template if absent):

   ```json
   {
     "linters": {
       ".zig": { "cmd": "zig fmt --check {file}", "warn_only": true }
     }
   }
   ```

   - `cmd` — single-file invocation with the `{file}` placeholder. The hook substitutes the validated changed path as `$1`, never string-glues it (injection-safe).
   - `warn_only` — `true` for pure formatters (formatting is not correctness); `false` for linters that catch real defects (those also drop a `.lintfail` session marker for the Stop-side gate).

   Keep the JSON valid (`jq . .assistant/lint-registry.json`). Do not touch the `size` block unless the user explicitly asks to change size thresholds.

3. Confirm to the user: the next edit to a `.<ext>` file will run the linter automatically. No hook change, no restart.

### 5. Offer /contribute (upstream the default)

If the linter is a generic, reusable default (not project-specific config), offer:

> Upstream this `.<ext>` linter default into the harness registry so every project gets it? → `/contribute`

`/contribute` opens the fork → PR that adds the extension to the harness's shipped `lint-registry.json` reference. This is where "unknown language → install linter → offer contribute" terminates. Skip the offer for project-specific configs.

## Guardrails

- **§11 stack-agnostic:** you add a linter the *user chose for their project*. Never impose one. A declined install leaves an inert row.
- **§12 no secrets:** installs go through the package manager; never write tokens into config or the registry.
- **Non-interactive hook / interactive skill:** all prompts live here. The hook only points here and never blocks (PostToolUse fires after the write).
- **English only** for all files written into the repo, per project convention.
