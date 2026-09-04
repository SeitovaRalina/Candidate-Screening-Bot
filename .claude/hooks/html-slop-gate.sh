#!/usr/bin/env bash
# @spec:REQ-HTML-SLOP-GATE
# PostToolUse (Edit|Write|MultiEdit) — auto anti-ai-slop pass on written HTML.
# When a *.html file is written/edited, strip tags/style/script, scan the VISIBLE
# text for high-precision slop markers (EN+RU). If the render reads AI-sloppy,
# block once with a de-slop nudge pointing /anti-ai-slop-writing at that file.
# Density scorer only — never an LLM "is this good?" (LLM judges reward verbosity).
# Loop-safe: caps at 1 block per (file, content-sha); a real de-slop changes the
# sha and lowers the marker count, so the re-write passes. Fail-open, O(1).
set -euo pipefail
fail_open() { exit 0; }
trap fail_open ERR
command -v jq >/dev/null 2>&1 || exit 0
command -v perl >/dev/null 2>&1 || exit 0

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STDIN="$(cat)"

FILE="$(printf '%s' "$STDIN" | jq -r '.tool_input.file_path // empty')"
[ -n "$FILE" ] || exit 0
case "$FILE" in
  *.html|*.htm) ;;
  *) exit 0 ;;
esac
[ -f "$FILE" ] || exit 0

# Visible text only: drop <script>/<style> bodies, then all tags, collapse space.
TEXT="$(perl -0777 -pe 's/<(script|style)\b[^>]*>.*?<\/\1>//gis; s/<[^>]+>/ /g; s/&[a-z]+;/ /gi; s/\s+/ /g' "$FILE" 2>/dev/null || echo)"
[ -n "$TEXT" ] || exit 0

WORDS="$(printf '%s' "$TEXT" | wc -w | tr -d ' ')"
[ "$WORDS" -gt 60 ] || exit 0   # skip tiny fragments/skeletons

# High-precision markers (curated from anti-ai-slop-writing/references/banned-words.md).
# Kept tight on purpose: shared guardrail, false positives are expensive.
MARKERS='delve|delving|tapestry|moreover|furthermore|meticulous|seamless|robust solution|comprehensive (analysis|overview|report)|cutting-edge|game-chang|transformative|unprecedented|testament to|in the realm of|navigating the|it'\''s important to note|it is important to note|it'\''s worth noting|at the end of the day|in conclusion|elevate your|unlock the|empower|стоит отметить|важно отметить|важно понимать|в современном мире|стоит подчеркнуть|играет (важную|ключевую) роль|не только.{0,40}но и|таким образом,|подчеркивает|в заключение|нельзя не отметить|отдельного внимания заслуживает'
HITS="$(printf '%s' "$TEXT" | grep -oiE "$MARKERS" | wc -l | tr -d ' ')"
[ "$HITS" -ge 3 ] || exit 0

# Cap: <=1 block per (file, content-sha).
SESS_DIR="$ROOT/.claude/sessions"; mkdir -p "$SESS_DIR" 2>/dev/null || exit 0
SHA="$(shasum -a 256 "$FILE" 2>/dev/null | cut -d' ' -f1 || echo)"
KEY="$(printf '%s' "$FILE" | shasum -a 256 | cut -d' ' -f1)"
STAMP="$SESS_DIR/${KEY}.htmlslop"
[ -f "$STAMP" ] && [ "$(cat "$STAMP" 2>/dev/null)" = "$SHA" ] && exit 0
printf '%s\n' "$SHA" > "$STAMP" 2>/dev/null || true

REL="${FILE#$ROOT/}"
REASON="anti-ai-slop auto-gate: '$REL' renders ${WORDS} words with ${HITS} slop markers. Run /anti-ai-slop-writing on this file — cut to the density the report warrants, delete the marker phrases (delve/seamless/важно отметить/…), keep it short and human-readable. Rewrite the file, don't just acknowledge."
jq -nc --arg reason "$REASON" '{decision:"block", reason:$reason}'
exit 0
