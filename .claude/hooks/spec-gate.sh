#!/usr/bin/env bash
# @spec:REQ-SPEC-GATE
# PreToolUse (Write|Edit|MultiEdit) — block edits to harness "source" without a clean,
# clarified spec for the branch. HARD only in production mode (.assistant/mode.json
# mode=production); advisory/absent mode => allow. Deny via permissionDecision, not exit 2.
# Spec: .assistant/component-specs/spec-gate.md (REQ-SPEC-GATE). Fail-open.
set -euo pipefail
trap 'exit 0' ERR
command -v jq >/dev/null 2>&1 || exit 0

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STDIN="$(cat)"
FILE="$(printf '%s' "$STDIN" | jq -r '.tool_input.file_path // empty')"
[ -n "$FILE" ] || exit 0

# Lexically collapse `.`/`..` segments in FILE BEFORE the glob match below — a raw `..` segment
# (e.g. $ROOT/x/../.claude/hooks/y.sh) doesn't match a `.claude/hooks/*` glob as a string, but
# the OS resolves it to the protected file anyway (path-traversal bypass around the
# spec-before-code gate). Pure string collapse, no filesystem stat — deliberately not chasing
# real symlinks: see self-config-guard.sh's canon_path comment for why (ROOT and a
# not-yet-existing FILE can't both be `pwd -P`-resolved, so doing it for one and not the other
# would desync the prefix-strip on a symlinked tree, e.g. macOS's /var -> /private/var).
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

# "Source" of the harness = executable behavior. Config/docs bypass.
case "$REL" in
  .claude/hooks/*|.claude/skills/*|.claude/agents/*) ;;
  *) exit 0 ;;
esac

# Mode: production gates; advisory (default) allows.
MODE_FILE="${HARNESS_MODE_FILE:-$ROOT/.assistant/mode.json}"
MODE="advisory"
[ -f "$MODE_FILE" ] && MODE="$(jq -r '.mode // "advisory"' "$MODE_FILE" 2>/dev/null || echo advisory)"
[ "$MODE" = "production" ] || exit 0

# Locate the active spec for this branch.
SLUG="${SPEC_GATE_SLUG:-$(git -C "$ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null | sed 's|.*/||' || echo)}"
DIRS="${SPEC_GATE_SPEC_DIRS:-$ROOT/.assistant/specs:$ROOT/.assistant/component-specs}"
SPEC=""
IFS=':' read -ra DD <<< "$DIRS"
for d in "${DD[@]}"; do
  [ -n "$SLUG" ] && [ -f "$d/$SLUG.md" ] && { SPEC="$d/$SLUG.md"; break; }
done

deny(){ jq -nc --arg r "$1" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'; exit 0; }

if [ -z "$SPEC" ]; then
  deny "spec-gate (production mode): no active spec for branch '$SLUG'. Run /elicit to write a spec before editing harness source ($REL). Add .assistant/specs/$SLUG.md, or switch mode to advisory."
fi
if grep -q '\[NEEDS CLARIFICATION' "$SPEC" 2>/dev/null; then
  deny "spec-gate (production mode): spec $SLUG.md still has [NEEDS CLARIFICATION] markers. Resolve them before writing code."
fi
if grep -qE '^- \[ \]' "$SPEC" 2>/dev/null; then
  deny "spec-gate (production mode): spec $SLUG.md has unchecked open items (- [ ]). Close them before writing code."
fi
exit 0
