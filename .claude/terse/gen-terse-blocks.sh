#!/usr/bin/env bash
# Effective Harness — terse block generator.
#
# Stamps a delimited "terse output" block into each .claude/agents/*.md body, rendered
# from the canonical ruleset in .claude/terse/ruleset.md at the level given by
# .claude/terse/classes.yml. Idempotent: re-running produces byte-identical files.
#
# Usage:
#   gen-terse-blocks.sh            stamp / refresh blocks in every agent
#   gen-terse-blocks.sh --clean    remove every stamped block (full reversibility)
#
# Env:
#   TERSE_AGENTS_DIR   override the agents dir (drift check points this at a temp copy)
#
# The block is delimited by:
#   <!-- harness-terse:start (generated ...) -->  ...  <!-- harness-terse:end -->
# and is inserted immediately after the frontmatter closing `---`, before the first heading.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TERSE_DIR="$ROOT/.claude/terse"
RULESET="$TERSE_DIR/ruleset.md"
CLASSES="$TERSE_DIR/classes.yml"
AGENTS_DIR="${TERSE_AGENTS_DIR:-$ROOT/.claude/agents}"

START_MARK='<!-- harness-terse:start (generated from .claude/terse/ruleset.md — do not edit by hand) -->'
END_MARK='<!-- harness-terse:end -->'

CLEAN=0
[ "${1:-}" = "--clean" ] && CLEAN=1

[ -f "$RULESET" ] || { echo "gen-terse-blocks: missing $RULESET" >&2; exit 1; }
[ -f "$CLASSES" ] || { echo "gen-terse-blocks: missing $CLASSES" >&2; exit 1; }

# --- extract a named section body from ruleset.md (between the section markers) ---
section() {
    awk -v tag="$1" '
        $0 == "<!-- terse-section: " tag " -->" { grab=1; next }
        $0 == "<!-- /terse-section: " tag " -->" { grab=0 }
        grab { print }
    ' "$RULESET"
}

CORE_BODY="$(section core)"
CARVEOUT_BODY="$(section carveout)"
[ -n "$CORE_BODY" ] || { echo "gen-terse-blocks: could not read core section from ruleset" >&2; exit 1; }
[ -n "$CARVEOUT_BODY" ] || { echo "gen-terse-blocks: could not read carveout section from ruleset" >&2; exit 1; }

# --- look up level + carveout for an agent name from classes.yml ---
# Emits "LEVEL CARVEOUT" (e.g. "full true"). Falls back to defaults.
lookup() {
    local name="$1"
    awk -v want="$name" '
        /^defaults:/ { in_def=1; in_agents=0; next }
        /^agents:/   { in_def=0; in_agents=1; next }
        in_def && /^[[:space:]]+level:/    { def_level=$2 }
        in_def && /^[[:space:]]+carveout:/ { def_carveout=$2 }
        in_agents {
            line=$0
            sub(/^[[:space:]]+/, "", line)
            # match "name:" possibly followed by "{ ... }"
            key=line
            sub(/:.*/, "", key)
            if (key == want) {
                lvl=def_level; cv=def_carveout
                if (match(line, /level:[[:space:]]*[a-z]+/)) {
                    m=substr(line, RSTART, RLENGTH); sub(/level:[[:space:]]*/, "", m); lvl=m
                }
                if (match(line, /carveout:[[:space:]]*(true|false)/)) {
                    m=substr(line, RSTART, RLENGTH); sub(/carveout:[[:space:]]*/, "", m); cv=m
                }
                print lvl, cv
                found=1
                exit
            }
        }
        END { if (!found) print def_level, def_carveout }
    ' "$CLASSES"
}

# --- build the full block text for a given level+carveout into stdout ---
render_block() {
    local carveout="$1"
    printf '%s\n' "$START_MARK"
    printf '%s\n' "$CORE_BODY"
    if [ "$carveout" = "true" ]; then
        printf '\n'
        printf '%s\n' "$CARVEOUT_BODY"
    fi
    printf '%s\n' "$END_MARK"
}

# --- strip any existing block (start..end inclusive) plus one trailing blank line ---
strip_block() {
    awk -v s="$START_MARK" -v e="$END_MARK" '
        $0 == s { inblk=1; next }
        inblk && $0 == e { inblk=0; skip_blank=1; next }
        inblk { next }
        skip_blank { skip_blank=0; if ($0 == "") next }
        { print }
    ' "$1"
}

# --- insert block after the frontmatter close (first `---` after the opening `---`) ---
# $1 = stripped file body on disk; $2 = path to a file holding the block text.
insert_block() {
    local file="$1" blockfile="$2"
    awk -v blockfile="$blockfile" '
        BEGIN {
            fence=0; done=0
            while ((getline line < blockfile) > 0) {
                block = block (block == "" ? "" : "\n") line
            }
            close(blockfile)
        }
        {
            print
            if (!done && $0 ~ /^---[[:space:]]*$/) {
                fence++
                if (fence == 2) {
                    print ""
                    print block
                    done=1
                }
            }
        }
    ' "$file"
}

changed=0
stamped=0
cleaned=0

tmp_stripped="$(mktemp)"
tmp_block="$(mktemp)"
trap 'rm -f "$tmp_stripped" "$tmp_block"' EXIT

shopt -s nullglob
for f in "$AGENTS_DIR"/*.md; do
    name="$(basename "$f" .md)"
    read -r level carveout < <(lookup "$name")
    level="${level:-full}"
    carveout="${carveout:-false}"

    strip_block "$f" > "$tmp_stripped"

    if [ "$CLEAN" -eq 1 ] || [ "$level" = "off" ]; then
        new="$(cat "$tmp_stripped")"
        [ "$CLEAN" -eq 1 ] && cleaned=$((cleaned + 1))
    else
        render_block "$carveout" > "$tmp_block"
        new="$(insert_block "$tmp_stripped" "$tmp_block")"
        stamped=$((stamped + 1))
    fi

    if [ "$new" != "$(cat "$f")" ]; then
        printf '%s\n' "$new" > "$f"
        changed=$((changed + 1))
    fi
done

if [ "$CLEAN" -eq 1 ]; then
    echo "gen-terse-blocks: --clean removed blocks from $cleaned agent(s); $changed file(s) rewritten."
else
    echo "gen-terse-blocks: stamped $stamped agent(s); $changed file(s) changed."
fi
