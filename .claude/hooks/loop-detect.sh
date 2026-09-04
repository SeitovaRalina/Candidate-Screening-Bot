#!/usr/bin/env bash
# @spec:REQ-LOOP-FEEDBACK
# PostToolUse — detect repeating-error / identical-action loops (T2).
# Soft notice only: PostToolUse cannot block. Writes to .claude/sessions/<id>.loopstate.
set -euo pipefail

fail_open() { exit 0; }
trap fail_open ERR

command -v jq >/dev/null 2>&1 || exit 0

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STDIN="$(cat)"

SESSION_ID="$(printf '%s' "$STDIN" | jq -r '.session_id // empty')"
TOOL_NAME="$(printf '%s' "$STDIN" | jq -r '.tool_name // empty')"
[ -n "$SESSION_ID" ] || exit 0
[ -n "$TOOL_NAME" ] || exit 0

SESS_DIR="$ROOT/.claude/sessions"
mkdir -p "$SESS_DIR" 2>/dev/null || exit 0
STATE="$SESS_DIR/${SESSION_ID}.loopstate"

sha256() {
    if command -v sha256sum >/dev/null 2>&1; then sha256sum | awk '{print $1}'
    else shasum -a 256 | awk '{print $1}'; fi
}

# Normalize tool_input (compact, key-sorted) so whitespace-only diffs don't dodge detection.
NORM_INPUT="$(printf '%s' "$STDIN" | jq -cS '.tool_input // {}' 2>/dev/null || printf '{}')"

# Error indicator from tool_response: presence of error + a short error string.
ERR_FLAG="$(printf '%s' "$STDIN" | jq -r '
  (.tool_response // {}) as $r
  | if ($r|type)=="object" then
      ((($r.is_error // $r.isError // false)|tostring) + "|" + (($r.error // $r.stderr // "")|tostring))
    else ($r|tostring) end' 2>/dev/null || printf 'false|')"
# Truncate error string so transient detail (timestamps, pids) noise is bounded.
ERR_FLAG="$(printf '%s' "$ERR_FLAG" | cut -c1-200)"

SIG="$(printf '%s\n%s\n%s' "$TOOL_NAME" "$NORM_INPUT" "$ERR_FLAG" | sha256)"
# Separate error-string signature for the "same error N×" rule (input may vary, error same).
# Gate on genuine failure, not on the mere presence of stderr text: Claude Code appends a
# benign "Shell cwd was reset to ..." notice to Bash stderr on every cwd-changing call, and
# without this gate that identical notice looked like a recurring error even though is_error
# is false and the call succeeded. When the flag key itself is absent (some non-Bash/MCP tool
# responses carry an .error with no boolean at all), fall back to ".error non-empty" — but
# never to .stderr, which is exactly the noisy field that caused the false positive.
IS_ERR="$(printf '%s' "$STDIN" | jq -r '
  (.tool_response // {}) as $r
  | if ($r|type)=="object" then
      (if ($r|has("is_error")) or ($r|has("isError"))
       then (($r.is_error // $r.isError // false)|tostring)
       else ((($r.error // "") != "")|tostring) end)
    else "false" end' 2>/dev/null || printf 'false')"
ERR_ONLY="$(printf '%s' "$ERR_FLAG" | cut -d'|' -f2-)"
ERR_SIG=""
if [ "$IS_ERR" = "true" ] && [ -n "$ERR_ONLY" ]; then
    ERR_SIG="$(printf '%s' "$ERR_ONLY" | sha256)"
fi

# Ring buffer: keep last 12 lines "<sig> <errsig>".
printf '%s %s\n' "$SIG" "$ERR_SIG" >> "$STATE"
tail -n 12 "$STATE" > "$STATE.tmp" 2>/dev/null && mv "$STATE.tmp" "$STATE" 2>/dev/null || true

SAME_SIG="$(awk -v s="$SIG" '$1==s{c++} END{print c+0}' "$STATE")"
SAME_ERR=0
if [ -n "$ERR_SIG" ]; then
    SAME_ERR="$(awk -v e="$ERR_SIG" '$2==e{c++} END{print c+0}' "$STATE")"
fi

# Feedback-inject (REQ-LOOP-FEEDBACK): deliver the reason via additionalContext so the model
# actually receives WHAT repeated and changes approach — not just a stderr note (ag20: a naive
# retry without a feedback signal loops on the same answer).
MSG=""
if [ "$SAME_SIG" -ge 3 ]; then
    MSG="LOOP DETECTED: tool '$TOOL_NAME' ran ${SAME_SIG}x with identical input and identical result. Do NOT repeat it — change approach (different input, tool, or strategy) or ask the user. What happened: ${ERR_ONLY:-identical no-op result}."
elif [ "$SAME_ERR" -ge 5 ]; then
    MSG="LOOP DETECTED: the same error has recurred ${SAME_ERR} times across recent tool calls. Retrying it again probably will not help, so try a different approach or ask the user for guidance. Recurring error: ${ERR_ONLY:-see prior output}."
fi

if [ -n "$MSG" ]; then
    printf '%s\n' "$MSG" >&2
    if command -v jq >/dev/null 2>&1; then
        jq -nc --arg c "$MSG" '{hookSpecificOutput:{hookEventName:"PostToolUse",additionalContext:$c}}'
    fi
fi

exit 0
