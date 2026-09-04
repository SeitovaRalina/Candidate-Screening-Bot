#!/usr/bin/env bash
# @spec:REQ-TRACE-GATE
# Stop — requirement traceability gate (trimmed: UNBOUND + ORPHAN, no STALE — CP-D).
# HARD only in production mode; advisory/absent => silent. Loop-safe (cap 2), fail-open.
# UNBOUND = an approved REQ id with no @spec:REQ-xxx anchor anywhere in the tree.
# ORPHAN  = an @spec:REQ-xxx anchor whose REQ id is not declared/approved.
# Spec: .assistant/component-specs/trace-gate.md (REQ-TRACE-GATE).
set -euo pipefail
trap 'exit 0' ERR
command -v jq >/dev/null 2>&1 || exit 0

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STDIN="$(cat)"
[ "$(printf '%s' "$STDIN" | jq -r '.stop_hook_active // false')" = "true" ] && exit 0
SESSION_ID="$(printf '%s' "$STDIN" | jq -r '.session_id // empty')"
[ -n "$SESSION_ID" ] || exit 0

MODE_FILE="${HARNESS_MODE_FILE:-$ROOT/.assistant/mode.json}"
MODE="advisory"; [ -f "$MODE_FILE" ] && MODE="$(jq -r '.mode // "advisory"' "$MODE_FILE" 2>/dev/null || echo advisory)"
[ "$MODE" = "production" ] || exit 0

SPEC_DIRS="${TRACE_SPEC_DIRS:-$ROOT/.assistant/specs:$ROOT/.assistant/component-specs}"
# installed-module component-specs also declare approved reqs (D-044); auto-append when default
if [ -z "${TRACE_SPEC_DIRS:-}" ]; then
  for md in "$ROOT"/modules/*/component-specs; do [ -d "$md" ] && SPEC_DIRS="$SPEC_DIRS:$md"; done
fi
SCAN_ROOT="${TRACE_SCAN_ROOT:-$ROOT}"

# only fire when this session touched a spec or source file (unless forced for tests)
if [ "${TRACE_FORCE:-0}" != "1" ]; then
  touched="$(git -C "$ROOT" diff --name-only HEAD 2>/dev/null | grep -E '(\.assistant/(specs|component-specs)/|\.claude/(hooks|skills|agents|lib)/)' || true)"
  [ -n "$touched" ] || exit 0
fi

# approved REQ ids
approved=""
IFS=':' read -ra DD <<< "$SPEC_DIRS"
for d in "${DD[@]}"; do
  [ -d "$d" ] || continue
  for f in "$d"/*.md; do
    [ -f "$f" ] || continue
    grep -q 'status: *approved' "$f" || continue
    id="$(grep -oE 'id: *REQ-[A-Za-z0-9-]+' "$f" | head -1 | sed 's/id: *//')"
    [ -n "$id" ] && approved+="$id"$'\n'
  done
done
# anchors present in the tree
if [ "$SCAN_ROOT" = "$ROOT" ] && git -C "$ROOT" rev-parse >/dev/null 2>&1; then
  anchors="$(git -C "$ROOT" grep -hoE '@spec:REQ-[A-Za-z0-9-]+' -- . 2>/dev/null | sed 's/@spec://' | sort -u || true)"
else
  anchors="$(grep -rhoE '@spec:REQ-[A-Za-z0-9-]+' "$SCAN_ROOT" 2>/dev/null | sed 's/@spec://' | sort -u || true)"
fi

UNBOUND=""; for id in $approved; do printf '%s\n' "$anchors" | grep -qxF "$id" || UNBOUND+="$id "; done
ORPHAN=""; for a in $anchors; do printf '%s\n' "$approved" | grep -qxF "$a" || ORPHAN+="$a "; done
[ -n "$UNBOUND$ORPHAN" ] || exit 0

# loop cap 2 per HEAD
SD="${HARNESS_SESS_DIR:-$ROOT/.claude/sessions}"; mkdir -p "$SD" 2>/dev/null || exit 0
CT="$SD/${SESSION_ID}.tracegate"; HEAD="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || echo x)"
ph=""; pc=0; [ -f "$CT" ] && { ph="$(cut -d' ' -f1 "$CT")"; pc="$(cut -d' ' -f2 "$CT")"; }
case "$pc" in ''|*[!0-9]*) pc=0;; esac
if [ "$ph" = "$HEAD" ]; then [ "$pc" -ge 2 ] && exit 0; nc=$((pc+1)); else nc=1; fi
printf '%s %s\n' "$HEAD" "$nc" > "$CT" 2>/dev/null || true

MSG="trace-gate:"
[ -n "$UNBOUND" ] && MSG="$MSG UNBOUND (approved req, no @spec: anchor): $UNBOUND."
[ -n "$ORPHAN" ]  && MSG="$MSG ORPHAN (@spec: anchor, no such approved req): $ORPHAN."
MSG="$MSG Add a '// @spec:REQ-xxx' anchor in the implementing file, or fix the id. (block $nc/2)"
jq -nc --arg r "$MSG" '{decision:"block",reason:$r,hookSpecificOutput:{hookEventName:"Stop",additionalContext:$r}}'
exit 0
