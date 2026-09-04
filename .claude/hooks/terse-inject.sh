#!/usr/bin/env bash
# @spec:REQ-TERSE-INJECT
# PreToolUse (Task/Agent) — inject a compact terse directive into subagents that
# do NOT already carry a stamped harness terse block (general-purpose, Explore,
# claude, unknown, plugin agents). Harness agents whose .claude/agents/<type>.md
# already contains "harness-terse:start" are skipped (no double-terse).
#
# NOTE: post ~v2.1.63 the Task tool arrives here as tool_name "Agent" and the
# full spawn is under tool_input (.subagent_type/.description/.prompt). Injection
# mechanism = returning hookSpecificOutput.updatedInput (a full tool_input
# replacement) — additionalContext is a no-op on PreToolUse.
#
# Off-switch: HARNESS_TERSE_TASK_HOOK=off. Never blocks; fail-open on any error.
set -euo pipefail

fail_open() { exit 0; }
trap fail_open ERR

[ "${HARNESS_TERSE_TASK_HOOK:-on}" = "off" ] && exit 0

command -v jq >/dev/null 2>&1 || exit 0

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STDIN="$(cat)"
[ -n "$STDIN" ] || exit 0

# Bail if stdin isn't valid JSON or carries no prompt to modify.
printf '%s' "$STDIN" | jq -e . >/dev/null 2>&1 || exit 0
PROMPT="$(printf '%s' "$STDIN" | jq -r '.tool_input.prompt // empty')"
[ -n "$PROMPT" ] || exit 0

SUBAGENT="$(printf '%s' "$STDIN" | jq -r '.tool_input.subagent_type // empty')"
# Reject anything but a bare agent-name charset before it's used in a path lookup below — an
# unsanitized value (e.g. containing `/` or `..`) could otherwise be interpolated into
# $ROOT/.claude/agents/${SUBAGENT}.md and probe/read paths outside that directory. Worst case
# here is only the terse-directive check being fooled (not code execution), but there's no
# reason to interpolate an unvalidated value into a path at all.
case "$SUBAGENT" in
    *[!A-Za-z0-9_-]*) SUBAGENT="" ;;
esac

# Skip agents that already carry a stamped terse block (no double-terse).
if [ -n "$SUBAGENT" ]; then
    AGENT_FILE="$ROOT/.claude/agents/${SUBAGENT}.md"
    if [ -f "$AGENT_FILE" ] && grep -q 'harness-terse:start' "$AGENT_FILE" 2>/dev/null; then
        exit 0
    fi
fi

read -r -d '' DIRECTIVE <<'EOF' || true
PLAIN OUTPUT — write compact, in ordinary English. Lead with the answer, justify briefly, say it once, no preamble/ceremony. Drop rhetorical scaffolding ("not X but Y", "the key distinction", "put differently"); use the literal relationship, not the metaphor ("required" not "gated", "outdated" not "stale"). Scope and numbers stay exact — never widen/narrow a claim.
EXACT — never compress: technical terms, identifiers, symbol names, CODE, file PATHS, commands, ERROR text, numbers/versions — verbatim.
Structured/YAML/JSON output: written normally (keys + values exact, valid).
User-facing artifacts (plan / PR body / commit message): normal prose, not compressed.
---
EOF

# Prepend the directive to the spawn prompt, return the full modified tool_input.
UPDATED_INPUT="$(printf '%s' "$STDIN" | jq -c \
    --arg d "$DIRECTIVE" \
    '.tool_input | .prompt = ($d + "\n" + .prompt)')"

jq -nc --argjson ti "$UPDATED_INPUT" \
    '{hookSpecificOutput:{hookEventName:"PreToolUse", updatedInput:$ti}}'
exit 0
