#!/usr/bin/env bash
# @spec:REQ-OFFLOAD-GATE
# PostToolUse — context-offload metric probe. STUB (CP-C): measures raw tool-output size
# and logs it; does NOT offload or block yet. The offload threshold is empirical (OQ-CE-2:
# does Claude Code already Layer-0 offload?) and must be set from real data before this
# gate enforces anything. Inert + fail-open by design.
# Spec: .assistant/component-specs/offload-gate.md (REQ-OFFLOAD-GATE).
set -euo pipefail
trap 'exit 0' ERR
command -v jq >/dev/null 2>&1 || exit 0

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STDIN="$(cat)"
SESSION_ID="$(printf '%s' "$STDIN" | jq -r '.session_id // "nosess"')"
TOOL="$(printf '%s' "$STDIN" | jq -r '.tool_name // "?"')"
SIZE="$(printf '%s' "$STDIN" | jq -r '(.tool_response // .tool_output // "") | tostring | length' 2>/dev/null || echo 0)"
case "$SIZE" in ''|*[!0-9]*) SIZE=0 ;; esac

SD="${HARNESS_SESS_DIR:-$ROOT/.claude/sessions}"
mkdir -p "$SD" 2>/dev/null || exit 0
printf '%s %s\n' "$TOOL" "$SIZE" >> "$SD/${SESSION_ID}.offload-metric" 2>/dev/null || true
exit 0
