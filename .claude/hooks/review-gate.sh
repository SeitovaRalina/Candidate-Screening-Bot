#!/usr/bin/env bash
# @spec:REQ-REVIEW-GATE
# Stop — mandatory review gate. HARD only in production mode: "done" is blocked until a
# separate-context review of the CURRENT changes passed. Review = .claude/.last-review.md
# with `verdict: CLEAN` and a `reviewed_sha:` matching the current uncommitted diff.
# Separate-context review is the hard requirement; a different model/provider is RECOMMENDED
# (set in the /spec-review skill + reviewer.md), not forced here. Loop-safe, fail-open.
# Spec: .assistant/component-specs/review-gate.md (REQ-REVIEW-GATE).
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

# only require review when the session actually changed source
if [ "${REVIEW_FORCE:-0}" != "1" ]; then
  touched="$(git -C "$ROOT" diff --name-only HEAD 2>/dev/null | grep -E '\.claude/(hooks|skills|agents|lib)/' || true)"
  [ -n "$touched" ] || exit 0
fi

CUR_SHA="${REVIEW_CURRENT_SHA:-$(git -C "$ROOT" diff HEAD 2>/dev/null | { shasum 2>/dev/null || sha256sum 2>/dev/null; } | cut -c1-12 || echo nogit)}"
RF="${REVIEW_FILE:-$ROOT/.claude/.last-review.md}"

block(){
  SD="${HARNESS_SESS_DIR:-$ROOT/.claude/sessions}"; mkdir -p "$SD" 2>/dev/null || exit 0
  CT="$SD/${SESSION_ID}.reviewgate"; HEAD="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || echo x)"
  ph=""; pc=0; [ -f "$CT" ] && { ph="$(cut -d' ' -f1 "$CT")"; pc="$(cut -d' ' -f2 "$CT")"; }
  case "$pc" in ''|*[!0-9]*) pc=0;; esac
  if [ "$ph" = "$HEAD" ]; then [ "$pc" -ge 2 ] && exit 0; nc=$((pc+1)); else nc=1; fi
  printf '%s %s\n' "$HEAD" "$nc" > "$CT" 2>/dev/null || true
  jq -nc --arg r "$1 (block $nc/2)" '{decision:"block",reason:$r,hookSpecificOutput:{hookEventName:"Stop",additionalContext:$r}}'
  exit 0
}

[ -f "$RF" ] || block "review-gate (production mode): source changed but no review yet. Run /spec-review (separate context; a different model/provider is recommended) before done."
VERDICT="$(grep -iE '^verdict:' "$RF" | head -1 | sed 's/[Vv]erdict: *//' | tr -d '[:space:]')"
RSHA="$(grep -iE '^reviewed_sha:' "$RF" | head -1 | sed 's/[Rr]eviewed_sha: *//' | tr -d '[:space:]')"
[ "$VERDICT" = "CLEAN" ] || block "review-gate (production mode): last review verdict is '${VERDICT:-none}', not CLEAN. Address the findings and re-review."
[ "$RSHA" = "$CUR_SHA" ] || block "review-gate (production mode): review is stale (reviewed ${RSHA:-none}, current $CUR_SHA). Re-run /spec-review on the current changes."
exit 0
