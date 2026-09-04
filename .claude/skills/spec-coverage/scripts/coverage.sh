#!/usr/bin/env bash
# Spec coverage report. Denominator = DECLARED (approved) requirements. Scans TRACKED files
# only (git grep), so gitignored corpora are skipped. @spec:REQ-SPEC-COVERAGE
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"; cd "$ROOT"
ANCHORS="$(git grep -hoE '@spec:REQ-[A-Za-z0-9-]+' -- . 2>/dev/null | sed 's/@spec://' | sort -u || true)"
printf '%-26s %-9s %-7s\n' "REQUIREMENT" "ANCHORED" "TESTED"
printf '%-26s %-9s %-7s\n' "-----------" "--------" "------"
tot=0; anc=0; tst=0
for f in .assistant/specs/*.md .assistant/component-specs/*.md modules/*/component-specs/*.md; do
  [ -f "$f" ] || continue
  grep -q 'status: *approved' "$f" || continue
  id="$(grep -oE 'id: *REQ-[A-Za-z0-9-]+' "$f" | head -1 | sed 's/id: *//')"
  [ -n "$id" ] || continue
  tot=$((tot+1)); a=no; t=no
  printf '%s\n' "$ANCHORS" | grep -qxF "$id" && { a=yes; anc=$((anc+1)); }
  # TESTED = a dedicated TEST FILE exists whose NAME maps to the requirement's anchored file
  # (e.g. .claude/hooks/spec-gate.sh -> tests/hooks/test_spec_gate.sh). Precise: matches on the
  # test filename, not content, and ignores generic basenames like SKILL.md (skills are prompts,
  # not unit-tested — they correctly read "no").
  if [ "$a" = yes ]; then
    for af in $(git grep -lE "@spec:$id" -- . 2>/dev/null); do
      n="$(basename "$af" | sed 's/\.[^.]*$//')"
      [ "$n" = "SKILL" ] && continue          # skill dir marker, not an identifying name
      n2="${n//-/_}"
      if git ls-files -- '*test*' 2>/dev/null | grep -qiE "(^|/|_)(${n}|${n2})([._]|$)"; then t=yes; break; fi
    done
    [ "$t" = yes ] && tst=$((tst+1))
  fi
  printf '%-26s %-9s %-7s\n' "$id" "$a" "$t"
done
echo
[ "$tot" -gt 0 ] || { echo "No approved requirements."; exit 0; }
printf 'Coverage: %d/%d anchored (%d%%), %d/%d tested (%d%%) — of DECLARED requirements.\n' \
  "$anc" "$tot" "$((anc*100/tot))" "$tst" "$tot" "$((tst*100/tot))"
