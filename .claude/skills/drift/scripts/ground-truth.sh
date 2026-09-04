#!/usr/bin/env bash
# Ground-truth inventory snapshot for /drift. Deterministic, cheap (ls/git/wc only, no model).
# Prints the authoritative current-state inventory the drift auditors diff every doc claim against.
# The point: a stale count survives only because nobody counted — so we count, every run, at HEAD
# (NOT delta-scoped: drift accumulates in files no recent commit touched). @spec:REQ-DRIFT
# set -u only: this is a report, not a gate — an unmatched glob (module with no skills) must not abort it.
set -u
ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"; cd "$ROOT"

hr() { printf '%s\n' "----------------------------------------"; }
names() { ls "$@" 2>/dev/null | sed 's#.*/##; s/\.md$//; s/\.sh$//' | sort | paste -sd' ' - ; }

echo "# GROUND TRUTH — $(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?') @ $(git rev-parse --short HEAD 2>/dev/null || echo '?')"
hr
echo "agents   : $(ls .claude/agents/*.md 2>/dev/null | wc -l | tr -d ' ')"
echo "  $(names .claude/agents/*.md)"
echo "skills   : $(ls -d .claude/skills/*/ 2>/dev/null | wc -l | tr -d ' ')"
echo "  $(ls -d .claude/skills/*/ 2>/dev/null | sed 's#.claude/skills/##; s#/##' | sort | paste -sd' ' -)"
echo "hooks    : $(ls .claude/hooks/*.sh 2>/dev/null | wc -l | tr -d ' ')"
echo "  $(names .claude/hooks/*.sh)"
echo "modules  : $(ls -d modules/*/ 2>/dev/null | wc -l | tr -d ' ')"
for m in modules/*/; do
  [ -d "$m" ] || continue
  mn="$(basename "$m")"
  ag="$(names "$m"agents/*.md 2>/dev/null)"; sk="$(ls -d "$m"skills/*/ 2>/dev/null | sed 's#.*/skills/##; s#/##' | sort | paste -sd' ' -)"
  echo "  $mn | agents: ${ag:-none} | skills: ${sk:-none} | seed: $([ -d "$m"seed ] && echo yes || echo no) | routing: $([ -f "$m"routing.md ] && echo yes || echo no) | specs: $(ls "$m"component-specs/*.md 2>/dev/null | wc -l | tr -d ' ')"
done
echo "workflows: $(ls .github/workflows/*.y*ml 2>/dev/null | wc -l | tr -d ' ')"
echo "  $(names .github/workflows/*.y*ml)"
hr
echo "VERSION  : $(cat VERSION 2>/dev/null || echo '?')"
echo "mode     : $([ -f .assistant/mode.json ] && jq -r '.mode' .assistant/mode.json 2>/dev/null || echo 'absent => advisory')  (enum: prototype|production; absent=>advisory)"
echo "last decisions: $(grep -oE '^#+ D-[0-9]+' .assistant/decisions.md 2>/dev/null | tail -3 | sed 's/^#* //' | paste -sd', ' -)"
hr

# --- spec traceability (core + installed modules) ---
SPEC_GLOBS=(.assistant/specs/*.md .assistant/component-specs/*.md modules/*/component-specs/*.md)
approved=""; for g in "${SPEC_GLOBS[@]}"; do for f in $g; do [ -f "$f" ] || continue
  grep -q 'status: *approved' "$f" || continue
  id="$(grep -oE 'id: *REQ-[A-Za-z0-9-]+' "$f" | head -1 | sed 's/id: *//')"; [ -n "$id" ] && approved+="$id"$'\n'
done; done
# real ids are UPPERCASE words; drop placeholder tokens from doc examples (REQ-x, REQ-XXX, REQ-<CAP>, ...)
anchors="$(git grep -hoE '@spec:REQ-[A-Za-z0-9-]+' -- . 2>/dev/null | sed 's/@spec://' \
  | grep -vE '[a-z]' | grep -vE '^REQ-(X+|Z|A|N|CAP|NAME)$' | sort -u || true)"
approved="$(printf '%s' "$approved" | sort -u | sed '/^$/d')"
echo "declared REQs (approved): $(printf '%s\n' "$approved" | sed '/^$/d' | wc -l | tr -d ' ')"
echo "distinct @spec anchors   : $(printf '%s\n' "$anchors" | sed '/^$/d' | wc -l | tr -d ' ')"
UNBOUND=""; for id in $approved; do printf '%s\n' "$anchors" | grep -qxF "$id" || UNBOUND+="$id "; done
ORPHAN="";  for a in $anchors;  do printf '%s\n' "$approved" | grep -qxF "$a"  || ORPHAN+="$a "; done
echo "UNBOUND (approved req, no anchor): ${UNBOUND:-none}"
echo "ORPHAN  (anchor, no approved req): ${ORPHAN:-none}"
hr
echo "# ROUTINES: cannot be verified from the repo — Claude routines live in the cloud dashboard,"
echo "# not in git. .memory-bank/tech-details/routines.md CLAIMS the set below; a human (or a routines"
echo "# manifest, if one exists) MUST confirm against the actual dashboard. This blind spot is exactly"
echo "# what let routines.md over-claim /reflect + /audit — treat every routine claim as UNVERIFIED."
grep -E '^\| R[0-9]' .memory-bank/tech-details/routines.md 2>/dev/null | sed 's/^/  claims: /' || echo "  (routines.md not found)"
