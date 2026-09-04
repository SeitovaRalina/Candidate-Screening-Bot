#!/usr/bin/env bash
# @spec:REQ-TEST-COUNT-GUARD
# Stop — flag if the working tree has FEWER test files than git HEAD, i.e. an
# agent deleted tests this session (ANTI-pattern from ag11, observed 5x:
# "agents delete failing tests then hide it"). Deterministic: count test files
# in HEAD vs the working tree. Advisory block (cap 2 per HEAD), fail-open.
set -euo pipefail

fail_open() { exit 0; }
trap fail_open ERR

command -v jq >/dev/null 2>&1 || exit 0

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STDIN="$(cat)"

STOP_ACTIVE="$(printf '%s' "$STDIN" | jq -r '.stop_hook_active // false')"
[ "$STOP_ACTIVE" = "true" ] && exit 0
SESSION_ID="$(printf '%s' "$STDIN" | jq -r '.session_id // empty')"
[ -n "$SESSION_ID" ] || exit 0

git -C "$ROOT" rev-parse HEAD >/dev/null 2>&1 || exit 0

# Test-file pattern: common conventions across languages.
PAT='(^|/)(test_|.*_test\.|.*\.test\.|.*\.spec\.|.*Test\.|.*Tests\.)|(^|/)(tests?|__tests__|spec)/'

count_head() { git -C "$ROOT" ls-tree -r --name-only HEAD | grep -ciE "$PAT" || true; }
# Count test files that ACTUALLY EXIST on disk — a plain `rm` leaves the path in
# the index (ls-files -c still lists it), so filter by existence to catch a
# working-tree deletion that was not staged.
count_wt() {
    git -C "$ROOT" ls-files -c -o --exclude-standard \
      | grep -iE "$PAT" \
      | while IFS= read -r f; do [ -e "$ROOT/$f" ] && printf '.\n'; done \
      | grep -c . || true
}

HEAD_N="$(count_head)"; HEAD_N="${HEAD_N:-0}"
WT_N="$(count_wt)";     WT_N="${WT_N:-0}"
case "$HEAD_N" in ''|*[!0-9]*) HEAD_N=0 ;; esac
case "$WT_N"   in ''|*[!0-9]*) WT_N=0 ;; esac

# Only fire when tests were REMOVED (working tree below the committed baseline).
[ "$WT_N" -lt "$HEAD_N" ] || exit 0
DROP=$((HEAD_N - WT_N))

# Loop-safety cap: <=2 blocks per HEAD.
SESS_DIR="$ROOT/.claude/sessions"
mkdir -p "$SESS_DIR" 2>/dev/null || exit 0
COUNTER="$SESS_DIR/${SESSION_ID}.testcountguard"
HEAD_SHA="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || echo no-git)"
PREV_HEAD=""; PREV_COUNT=0
if [ -f "$COUNTER" ]; then
    PREV_HEAD="$(cut -d' ' -f1 "$COUNTER" 2>/dev/null || echo)"
    PREV_COUNT="$(cut -d' ' -f2 "$COUNTER" 2>/dev/null || echo 0)"
fi
case "$PREV_COUNT" in ''|*[!0-9]*) PREV_COUNT=0 ;; esac
if [ "$PREV_HEAD" = "$HEAD_SHA" ]; then
    [ "$PREV_COUNT" -ge 2 ] && exit 0
    NEW_COUNT=$((PREV_COUNT + 1))
else
    NEW_COUNT=1
fi
printf '%s %s\n' "$HEAD_SHA" "$NEW_COUNT" > "$COUNTER" 2>/dev/null || true

REASON="test-count-guard: working tree has ${WT_N} test files vs ${HEAD_N} at HEAD ($DROP removed this session). Deleting tests to make a suite pass is a known agent ANTI-pattern (ag11). Restore the tests, or if the removal is intentional, state which tests were deleted and why before ending."
CTX="$REASON  (Block ${NEW_COUNT}/2 at this commit.)"
jq -nc --arg reason "$REASON" --arg ctx "$CTX" \
    '{decision:"block", reason:$reason, hookSpecificOutput:{hookEventName:"Stop", additionalContext:$ctx}}'
exit 0
