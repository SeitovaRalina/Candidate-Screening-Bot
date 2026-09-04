#!/usr/bin/env bash
# @spec:REQ-LINT-SETUP
# PostToolUse (Edit|Write|MultiEdit) — per-file-change lint dispatcher (T1/T6/F1).
# For the ONE file just changed: (a) deterministic SIZE gate (maintainability /
# diff-blast-radius WARN), (b) a per-extension linter resolved from
# .assistant/lint-registry.json, run only if its binary is on PATH.
# PostToolUse fires AFTER the write and cannot block, so this is soft-notice only:
# emit LINT-WARN to stderr, drop a session marker for a future Stop-side gate, and
# ALWAYS exit 0 (fail-open). Never imposes a stack (§11): the registry ships empty;
# /lint-setup fills it per project.
set -euo pipefail

fail_open() { exit 0; }
trap fail_open ERR

command -v jq >/dev/null 2>&1 || exit 0

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STDIN="$(cat)"

FILE="$(printf '%s' "$STDIN" | jq -r '.tool_input.file_path // empty')"
[ -n "$FILE" ] || exit 0
[ -f "$FILE" ] || exit 0

SESSION_ID="$(printf '%s' "$STDIN" | jq -r '.session_id // empty')"
REL="${FILE#"$ROOT"/}"
REGISTRY="$ROOT/.assistant/lint-registry.json"
SESS_DIR="$ROOT/.claude/sessions"

# --- registry-driven skip list (extends the built-in skip set) ---------------
is_skipped() {
    local p="$1"
    case "$p" in
        *.md|*.json|*.lock|*.png|*.jpg|*.jpeg|*.svg|*.txt|*.ico) return 0 ;;
        */swarm-report/*|swarm-report/*|*/.memory-bank/*|.memory-bank/*) return 0 ;;
        */node_modules/*|*/.git/*|*/dist/*|*/build/*) return 0 ;;
    esac
    if [ -f "$REGISTRY" ]; then
        local extra
        extra="$(jq -r '.skip[]? // empty' "$REGISTRY" 2>/dev/null || echo)"
        local pat
        while IFS= read -r pat; do
            [ -n "$pat" ] || continue
            case "$p" in *"$pat"*) return 0 ;; esac
        done <<EOF
$extra
EOF
    fi
    return 1
}

is_skipped "$REL" && exit 0

# --- DEBOUNCE: skip re-lint if same (session,file) linted < N seconds ago -----
DEBOUNCE_SECS=15
mkdir -p "$SESS_DIR" 2>/dev/null || exit 0
if [ -n "$SESSION_ID" ]; then
    # A per-(session,file) marker; hash keeps the filename flat + safe.
    KEY="$(printf '%s\n%s' "$SESSION_ID" "$FILE" | (shasum -a 256 2>/dev/null || sha256sum 2>/dev/null) | cut -d' ' -f1)"
    DEB_MARKER="$SESS_DIR/${SESSION_ID}.lintdebounce.${KEY}"
    if [ -f "$DEB_MARKER" ]; then
        now="$(date +%s)"
        then_ts="$(cat "$DEB_MARKER" 2>/dev/null || echo 0)"
        case "$then_ts" in ''|*[!0-9]*) then_ts=0 ;; esac
        if [ $((now - then_ts)) -lt "$DEBOUNCE_SECS" ]; then
            exit 0
        fi
    fi
    date +%s > "$DEB_MARKER" 2>/dev/null || true
fi

# --- SIZE gate (deterministic, language-agnostic, cheapest first) ------------
# Framed as a maintainability / diff-blast-radius guardrail, NOT "LLMs degrade".
FILE_LOC_SOFT=400
FILE_LOC_HARD=800
LINE_LEN=120
if [ -f "$REGISTRY" ]; then
    v="$(jq -r '.size.file_loc_soft // empty' "$REGISTRY" 2>/dev/null || echo)"; case "$v" in ''|*[!0-9]*) ;; *) FILE_LOC_SOFT="$v" ;; esac
    v="$(jq -r '.size.file_loc_hard // empty' "$REGISTRY" 2>/dev/null || echo)"; case "$v" in ''|*[!0-9]*) ;; *) FILE_LOC_HARD="$v" ;; esac
    v="$(jq -r '.size.line_len // empty' "$REGISTRY" 2>/dev/null || echo)"; case "$v" in ''|*[!0-9]*) ;; *) LINE_LEN="$v" ;; esac
fi

LOC="$(grep -c '' "$FILE" 2>/dev/null || echo 0)"
case "$LOC" in ''|*[!0-9]*) LOC=0 ;; esac

if [ "$LOC" -gt "$FILE_LOC_HARD" ]; then
    echo "LINT-WARN: '$REL' is $LOC lines (> $FILE_LOC_HARD hard). Large file — maintainability / diff-blast-radius concern; consider splitting." >&2
elif [ "$LOC" -gt "$FILE_LOC_SOFT" ]; then
    echo "LINT-WARN: '$REL' is $LOC lines (> $FILE_LOC_SOFT soft). Growing large — keep an eye on blast radius." >&2
fi

LONGLINES="$(awk -v n="$LINE_LEN" 'length > n {c++} END {print c+0}' "$FILE" 2>/dev/null || echo 0)"
case "$LONGLINES" in ''|*[!0-9]*) LONGLINES=0 ;; esac
if [ "$LONGLINES" -gt 0 ]; then
    echo "LINT-WARN: '$REL' has $LONGLINES line(s) over $LINE_LEN cols." >&2
fi

# --- resolve a per-extension linter from the registry ------------------------
EXT=".${REL##*.}"
# No extension (e.g. Makefile, Dockerfile) → size gate only, no linter dispatch.
[ "$EXT" = ".$REL" ] && exit 0

LINTER_CMD=""
if [ -f "$REGISTRY" ]; then
    LINTER_CMD="$(jq -r --arg e "$EXT" '.linters[$e].cmd // empty' "$REGISTRY" 2>/dev/null || echo)"
fi

# Registry present but ext absent → unknown language: point at /lint-setup once.
if [ -z "$LINTER_CMD" ]; then
    echo "LINT-WARN: no linter configured for '$EXT' (file $REL). Run /lint-setup to add one." >&2
    if [ -n "$SESSION_ID" ]; then
        SETUP_MARKER="$SESS_DIR/${SESSION_ID}.lintsetup"
        grep -qxF "$EXT" "$SETUP_MARKER" 2>/dev/null || echo "$EXT" >> "$SETUP_MARKER" 2>/dev/null || true
    fi
    exit 0
fi

# Explicit silence: registry entry with empty cmd disables linting for this ext.
# (Handled above — empty cmd is indistinguishable from absent by design; both
#  point at /lint-setup. A project silencing an ext should drop it from .skip
#  or set the cmd to ':' if it wants a true no-op.)

BIN="${LINTER_CMD%% *}"
command -v "$BIN" >/dev/null 2>&1 || exit 0

WARN_ONLY="$(jq -r --arg e "$EXT" '.linters[$e].warn_only // false' "$REGISTRY" 2>/dev/null || echo true)"

# {file} placeholder → the already-validated changed path, passed as $1 (never
# string-glued into the shell — injection-safe).
RUN_CMD="${LINTER_CMD//\{file\}/\$1}"

# --- pure-bash watchdog: `timeout` is absent on macOS. Kill a slow linter -----
LINT_TIMEOUT=8
LINT_OUT=""
run_with_watchdog() {
    local out
    out="$(
        # `set -m` gives the backgrounded linter its own process group (pgid == its pid), so
        # `kill -- "-$cmd_pid"` below can signal the whole group, not just the immediate
        # subshell — a linter that forks (e.g. spawns a worker process) would otherwise leave
        # that child running past the timeout.
        set -m
        bash -c "$RUN_CMD" _ "$FILE" 2>&1 &
        cmd_pid=$!
        ( sleep "$LINT_TIMEOUT"; kill -- "-$cmd_pid" 2>/dev/null ) &
        watcher=$!
        wait "$cmd_pid" 2>/dev/null
        kill "$watcher" 2>/dev/null
    )" || true
    LINT_OUT="$out"
}
run_with_watchdog

if [ -n "$LINT_OUT" ]; then
    # PostToolUse cannot block; parse/lint findings are surfaced WARN-only and,
    # for non-warn-only linters, backed by a session marker a future Stop-side
    # gate can read. Never blocks here.
    printf 'LINT-WARN: %s findings on %s:\n%s\n' "$BIN" "$REL" "$LINT_OUT" >&2
    if [ "$WARN_ONLY" != "true" ] && [ -n "$SESSION_ID" ]; then
        FAIL_MARKER="$SESS_DIR/${SESSION_ID}.lintfail"
        grep -qxF "$REL" "$FAIL_MARKER" 2>/dev/null || echo "$REL" >> "$FAIL_MARKER" 2>/dev/null || true
    fi
fi

exit 0
