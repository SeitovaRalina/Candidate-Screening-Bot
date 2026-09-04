#!/usr/bin/env bash
# @spec:REQ-SPEC-LINT
# PostToolUse (Edit|Write|MultiEdit) — requirement-quality smell linter for spec files.
# ADVISORY: warns to stderr, never blocks (requirement smells are guidance, not errors).
# Scope: only spec files (.assistant/component-specs/*.md, */specs/*.md). Fail-open.
# Spec: .assistant/component-specs/spec-lint.md (REQ-SPEC-LINT).
set -euo pipefail
trap 'exit 0' ERR
command -v jq >/dev/null 2>&1 || exit 0

STDIN="$(cat)"
FILE="$(printf '%s' "$STDIN" | jq -r '.tool_input.file_path // empty')"
[ -n "$FILE" ] || exit 0
[ -f "$FILE" ] || exit 0

# Only lint spec files.
case "$FILE" in
  *.assistant/component-specs/*.md|*/specs/*.md|*.assistant/specs/*) ;;
  *) exit 0 ;;
esac

WEAK='\b(process|processes|perform|performs|make|makes|handle|handles|manage|manages|support|supports|appropriate|suitable|easy|fast|flexible|robust|seamless|efficient)\b'
EARS='\b(WHEN|IF|WHILE|WHERE|SHALL)\b'

WARN=""
# (a) weak-verb lines
while IFS= read -r ln; do
  WARN+="  weak/vague wording: ${ln}"$'\n'
done < <(grep -nEi "$WEAK" "$FILE" 2>/dev/null | head -20 || true)

# (b) requirement bullets inside a Requirements section lacking an EARS keyword
IN_REQ=0
n=0
while IFS= read -r line; do
  n=$((n+1))
  case "$line" in
    "## Requirements"*|"## Требования"*) IN_REQ=1; continue ;;
    "## "*) IN_REQ=0; continue ;;
  esac
  [ "$IN_REQ" = "1" ] || continue
  case "$line" in
    "- "*|"* "*)
      if ! printf '%s' "$line" | grep -qEi "$EARS"; then
        WARN+="  not checkable (no WHEN/IF/WHILE/WHERE/SHALL): ${n}:${line}"$'\n'
      fi
      ;;
  esac
done < "$FILE"

[ -n "$WARN" ] || exit 0
REL="${FILE##*/}"
printf 'SPEC-LINT-WARN: %s\n%s' "$REL" "$WARN" >&2
exit 0
