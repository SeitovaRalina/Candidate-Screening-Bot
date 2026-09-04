#!/usr/bin/env bash
# @spec:REQ-MODE-GATE
# PreToolUse (Write|Edit|MultiEdit) — the single mode enforcer. In PROTOTYPE mode, prototype
# output must not touch production source: block writes to paths OUTSIDE the prototype sandbox.
# Advisory/production/absent mode => allow (production mode is enforced by spec-gate/review-gate). Fail-open.
# Sandbox dir defaults to `prototype/`; override with PROTOTYPE_DIR. Spec: component-specs/mode-gate.md.
set -euo pipefail
trap 'exit 0' ERR
command -v jq >/dev/null 2>&1 || exit 0

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STDIN="$(cat)"
FILE="$(printf '%s' "$STDIN" | jq -r '.tool_input.file_path // empty')"
[ -n "$FILE" ] || exit 0

# Lexically collapse `.`/`..` segments in FILE BEFORE the glob match below — a raw `..` segment
# doesn't match the sandbox/allowlist globs as a string, but the OS resolves it to the real
# target anyway (path-traversal bypass around the prototype-mode sandbox). Pure string collapse,
# no filesystem stat — deliberately not chasing real symlinks: see self-config-guard.sh's
# canon_path comment for why (ROOT and a not-yet-existing FILE can't both be `pwd -P`-resolved,
# so doing it for one and not the other would desync the prefix-strip on a symlinked tree, e.g.
# macOS's /var -> /private/var).
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
REL="${FILE#"$ROOT"/}"

MODE_FILE="${HARNESS_MODE_FILE:-$ROOT/.assistant/mode.json}"
MODE="advisory"; [ -f "$MODE_FILE" ] && MODE="$(jq -r '.mode // "advisory"' "$MODE_FILE" 2>/dev/null || echo advisory)"
[ "$MODE" = "prototype" ] || exit 0

SANDBOX="${PROTOTYPE_DIR:-prototype/}"
# allow: inside the sandbox, or harness/config/docs surfaces (never app source)
case "$REL" in
  "$SANDBOX"*|.assistant/*|.memory-bank/*|.claude/*|*.md|.gitignore) exit 0 ;;
esac

jq -nc --arg r "mode-gate (prototype): prototype output must stay in the sandbox ($SANDBOX). Writing to production source ($REL) is blocked in prototype mode — promote to production first (/elicit → spec → review), or put this under $SANDBOX." \
  '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
exit 0
