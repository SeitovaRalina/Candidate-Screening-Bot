#!/usr/bin/env bash
# @spec:REQ-SELF-CONFIG-GUARD
# PreToolUse (Edit|Write|MultiEdit) — block an agent from rewriting its OWN
# governing config mid-session (harness self-modification / rule-drift attack,
# ANTI-pattern from ag11 + df01: "agent must not modify its own config").
#
# SCOPED to CONSUMING projects only: active iff a `.harness-lock` exists at the
# project root. In the harness SOURCE repo (no lock) editing .claude/ IS the job,
# so the guard is inert. Fail-open on any error.
set -euo pipefail

fail_open() { exit 0; }
trap fail_open ERR

command -v jq >/dev/null 2>&1 || exit 0

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# Only guard consuming installs; the harness source has no .harness-lock.
[ -f "$ROOT/.harness-lock" ] || exit 0

STDIN="$(cat)"
FILE="$(printf '%s' "$STDIN" | jq -r '.tool_input.file_path // empty')"
[ -n "$FILE" ] || exit 0

# Lexically collapse `.`/`..` segments in FILE BEFORE the glob match below — a raw `..` segment
# (e.g. $ROOT/x/../.claude/hooks/self-config-guard.sh) doesn't match a `.claude/*` glob as a
# string, but the OS resolves it to the protected file anyway (path-traversal bypass). Pure
# string collapse, no filesystem stat: works whether or not the path (or its parent dir) exists
# yet, and deliberately does NOT chase real symlinks — resolving symlinks via `cd`+`pwd -P` would
# require doing the same to ROOT above to keep the prefix-strip below meaningful, and ROOT and a
# not-yet-existing FILE can't both be resolved that way (a missing dir can't be `cd`'d into), so
# the two would go out of sync on any tree reached through a symlink component (e.g. macOS's
# /var -> /private/var, hit in this repo's own tests via `mktemp -d`) — a correctness regression
# with no attack this closes, since the finding's PoC is purely lexical (`../`), not symlink-based.
canon_path() {
    local f="$1" seg out=""
    local IFS='/'
    for seg in $f; do
        case "$seg" in
            ''|'.') ;;
            '..') out="${out%/*}" ;;
            *) out="$out/$seg" ;;
        esac
    done
    printf '%s' "$out"
}
FILE="$(canon_path "$FILE")"

# Path relative to project root (best effort).
REL="${FILE#"$ROOT"/}"

# Saved workflows are work product, not governing config (WFT-18f) — carve out before the
# .claude/* deny arm, or the registry convention (WFT-30..32) is dead on arrival in every
# consuming install.
case "$REL" in
  .claude/workflows/*)
    exit 0
    ;;
esac

# Governing-config surfaces an agent must not silently rewrite.
case "$REL" in
  .claude/*|CLAUDE.md|AGENTS.md|.assistant/INVARIANTS.md|.assistant/lint-registry.json|.harness-lock)
    REASON="self-config-guard: \`$REL\` is harness-governing config. An agent must not rewrite its own rules/hooks/agents mid-task (rule-drift ANTI-pattern). Change harness config deliberately via \`/sync\` or a human edit, not as a side effect of a feature task. If this edit is intentional harness work, do it in the harness source repo (which has no .harness-lock and no guard)."
    jq -nc --arg r "$REASON" \
      '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
    exit 0
    ;;
esac
exit 0
