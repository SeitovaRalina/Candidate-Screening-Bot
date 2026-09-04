#!/usr/bin/env bash
# @spec:REQ-WORKFLOW-TIER-GATE
# PreToolUse (Workflow) — deny a Workflow script that contains an agent() call missing a
# literal model/effort tier (REQ-WORKFLOW-TIER, WFT-10..22). The detector lives at
# .claude/lib/tier-scan.js (vendored acorn AST parser) — this hook only shells out to it and
# turns its verdict into permissionDecision.
#
# Mode-independent (WFT-15): never reads .assistant/mode.json, unlike mode-gate.sh. A missing
# model is a decidable defect, not a matter of taste — same always-on class as
# self-config-guard.sh. Off-switch: HARNESS_TIER_GATE=off (WFT-15a). Fail-open on any breakage
# (WFT-16): missing jq/node, missing detector, malformed stdin, or a detector parseError all
# exit 0 rather than block. Fan-out warning (WFT-20/21) is warn-only and never denies.
#
# WFT-18 vendor-checksum gate: before trusting .claude/lib/{acorn,walk}.js, verify each against
# the SHA-256 recorded in .claude/lib/VENDOR.md (read, never hardcoded here — VENDOR.md is the
# single source of truth so the two copies cannot drift). A mismatch, an unreadable VENDOR.md,
# or a missing `shasum` still fails OPEN per the repo's hook convention (WFT-16) — but unlike a
# generic fail-open this one is never silent: the cause is appended to
# .claude/sessions/tierwarn.log as `vendor_checksum_inert=1 cause=<cause> ...` so /routing-audit
# can count it, matching the existing fan-out warning line's format/dir. Causes emitted (for
# inject-state.sh's `workflow-tier-gate: INERT: <cause>` banner, kept in sync by hand):
#   vendor-doc-unreadable      — VENDOR.md missing or has no parseable SHA-256 table
#   shasum-unavailable         — no `shasum` binary on PATH
#   checksum-mismatch:<path>   — computed hash (or missing file) doesn't match VENDOR.md for <path>
#
# Deliberately NOT gated behind a cheap size-only pre-check or cached across calls: a same-size
# tamper would pass a size-only check silently, which is exactly the failure mode this exists to
# catch, and hashing two files totalling ~260KB is single-digit milliseconds — cheap enough on
# every invocation that a cache's staleness risk (stale mtime, cross-session drift) isn't worth
# taking on. Correctness over cleverness, per the spec's own priority order.
set -euo pipefail

fail_open() { exit 0; }
trap fail_open ERR

[ "${HARNESS_TIER_GATE:-on}" = "off" ] && exit 0

command -v jq >/dev/null 2>&1 || exit 0

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DETECTOR="$ROOT/.claude/lib/tier-scan.js"
command -v node >/dev/null 2>&1 || exit 0
[ -f "$DETECTOR" ] || exit 0

VENDOR_FAIL_CAUSE=""

log_tierwarn() {
    local sd ts
    sd="${HARNESS_SESS_DIR:-$ROOT/.claude/sessions}"
    mkdir -p "$sd" 2>/dev/null || return 0
    ts="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown)"
    printf '%s %s\n' "$ts" "$1" >> "$sd/tierwarn.log" 2>/dev/null || true
}

# D-051: separate log from tierwarn.log — this one is the safety-net tally /routing-audit reads
# (section 5, "launches-anyway" count). Same line format on purpose (timestamp + space-separated
# key=value pairs) so both logs stay parseable by the same convention.
log_tierpreflight() {
    local sd ts
    sd="${HARNESS_SESS_DIR:-$ROOT/.claude/sessions}"
    mkdir -p "$sd" 2>/dev/null || return 0
    ts="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown)"
    printf '%s %s\n' "$ts" "$1" >> "$sd/tierpreflight.log" 2>/dev/null || true
}

# Pure-bash watchdog (mirrors lint-gate.sh's run_with_watchdog): `timeout` is absent on macOS.
# A pathological script (e.g. one that makes the parser loop) must not hang this PreToolUse
# hook indefinitely — kill the node process after NODE_TIMEOUT seconds and treat that as a
# parse failure (fail-open, same as any other detector breakage per WFT-16).
NODE_TIMEOUT=8
run_node_with_watchdog() {
    local mode="$1" target="$2" out
    out="$(
        if [ "$mode" = "stdin" ]; then
            printf '%s' "$target" | node "$DETECTOR" --stdin 2>/dev/null &
        else
            node "$DETECTOR" "$target" 2>/dev/null &
        fi
        cmd_pid=$!
        ( sleep "$NODE_TIMEOUT"; kill "$cmd_pid" 2>/dev/null ) &
        watcher=$!
        wait "$cmd_pid" 2>/dev/null
        kill "$watcher" 2>/dev/null
    )" || true
    printf '%s' "$out"
}

# D-051: same watchdog shape as run_node_with_watchdog, dedicated rather than parameterized —
# macOS ships bash 3.2 as /usr/bin/env bash's resolution, and "${arr[@]}" on an EMPTY array under
# `set -u` throws "unbound variable" on that version, so a `flag="${3:-}"` + optional-array
# approach is not safe here. A second small function costs nothing this hook doesn't already pay
# elsewhere (tier-scan.js itself duplicates rather than shares state across its --signals/--stdin
# paths for the same kind of reason).
run_preflight_with_watchdog() {
    local mode="$1" target="$2" out
    out="$(
        if [ "$mode" = "stdin" ]; then
            printf '%s' "$target" | node "$DETECTOR" --preflight --stdin 2>/dev/null &
        else
            node "$DETECTOR" --preflight "$target" 2>/dev/null &
        fi
        cmd_pid=$!
        ( sleep "$NODE_TIMEOUT"; kill "$cmd_pid" 2>/dev/null ) &
        watcher=$!
        wait "$cmd_pid" 2>/dev/null
        kill "$watcher" 2>/dev/null
    )" || true
    printf '%s' "$out"
}

# Verify .claude/lib/{acorn,walk}.js against the SHA-256 table in VENDOR.md. On success returns
# 0. On any failure sets VENDOR_FAIL_CAUSE and returns 1 — caller decides fail-open + logging.
verify_vendor_checksums() {
    local vendor_md table line expected file actual
    vendor_md="$ROOT/.claude/lib/VENDOR.md"
    if [ ! -f "$vendor_md" ]; then
        VENDOR_FAIL_CAUSE="vendor-doc-unreadable"
        return 1
    fi
    command -v shasum >/dev/null 2>&1 || { VENDOR_FAIL_CAUSE="shasum-unavailable"; return 1; }

    # The "## Verify" fenced block in VENDOR.md is already `<hex>  <path>` — shasum -c's own
    # input format — so lift those lines directly rather than re-parsing the prose table above it.
    table="$(grep -E '^[0-9a-f]{64}  \.claude/lib/[A-Za-z0-9_.-]+\.js$' "$vendor_md" 2>/dev/null)" || true
    if [ -z "$table" ]; then
        VENDOR_FAIL_CAUSE="vendor-doc-unreadable"
        return 1
    fi

    while IFS= read -r line; do
        [ -n "$line" ] || continue
        expected="${line%%  *}"
        file="${line#*  }"
        if [ ! -f "$ROOT/$file" ]; then
            VENDOR_FAIL_CAUSE="checksum-mismatch:$file"
            return 1
        fi
        actual="$(shasum -a 256 "$ROOT/$file" 2>/dev/null | awk '{print $1}')" || true
        if [ "$actual" != "$expected" ]; then
            VENDOR_FAIL_CAUSE="checksum-mismatch:$file"
            return 1
        fi
    done <<TABLE_EOF
$table
TABLE_EOF

    return 0
}

STDIN="$(cat)"
printf '%s' "$STDIN" | jq -e . >/dev/null 2>&1 || exit 0

# Hoisted once: reused by the vendor-checksum failure branch, the WFT-20/21 fan-out warning, and
# the D-051 tier-preflight block below — all three want the same session_id for their log lines.
SESSION_ID="$(printf '%s' "$STDIN" | jq -r '.session_id // "unknown"')"

# WFT-10b revisited 2026-08-08: this used to grant blanket amnesty on the presence of
# `resumeFromRunId` alone, on the theory that "a resume replays a fixed, already-tiered prefix".
# Checked against the Agent SDK's own documented resumeFromRunId semantics before touching this:
# "edit-and-resume" is an intended, documented pattern — a resumed run replays the cached prefix
# from cache but genuinely RE-EXECUTES, live, "everything lexically after" the edited call, using
# whatever script content is submitted alongside resumeFromRunId in that same tool_input (cached
# results are matched by positional call index, the same contract Claude Code itself uses). That
# falsifies "the prefix was fixed at original authoring" for anything after the resume point —
# presence of resumeFromRunId said nothing about whether the accompanying script had ever been
# tiered-checked. Whether a GIVEN resumed run's script actually matches what was originally
# tiered is not verifiable from a hook at all (no access to the SDK's run journal) — that residual
# risk is recorded in .assistant/decisions.md rather than silently declared fixed.
# What IS closable from here: stop granting amnesty on presence alone. Falling through to the
# normal script/scriptPath/name detection below closes it — a genuine "pure" resume that carries
# none of those fields still has nothing to scan and allows via the existing TARGET="" branch, so
# this changes nothing for that case; only a resume that also carries fresh script content now
# gets scanned like any other invocation. A malformed run-id is logged for /routing-audit but
# never itself gates allow/deny — format validity says nothing about the accompanying script.
RESUME="$(printf '%s' "$STDIN" | jq -r '.tool_input.resumeFromRunId // empty')"
if [ -n "$RESUME" ] && ! printf '%s' "$RESUME" | grep -qE '^[A-Za-z0-9_-]+$'; then
    log_tierwarn "malformed_resume_run_id=1"
fi

SCRIPT="$(printf '%s' "$STDIN" | jq -r '.tool_input.script // empty')"
SCRIPT_PATH="$(printf '%s' "$STDIN" | jq -r '.tool_input.scriptPath // empty')"
NAME="$(printf '%s' "$STDIN" | jq -r '.tool_input.name // empty')"

TARGET=""
if [ -n "$SCRIPT" ]; then
    TARGET="stdin"
elif [ -n "$SCRIPT_PATH" ]; then
    TARGET="path:$SCRIPT_PATH"
elif [ -n "$NAME" ]; then
    # WFT-10a: no script to inspect for a named invocation unless it resolves to a registered,
    # reviewed workflow file. Allow unconditionally otherwise — denying breaks /deep-research.
    REGISTERED="$ROOT/.claude/workflows/${NAME}.js"
    if [ -f "$REGISTERED" ]; then
        TARGET="path:$REGISTERED"
    else
        exit 0
    fi
else
    exit 0
fi

# About to trust the vendored parser with a real script — verify it first (WFT-18).
if ! verify_vendor_checksums; then
    log_tierwarn "vendor_checksum_inert=1 cause=$VENDOR_FAIL_CAUSE session=$SESSION_ID"
    exit 0
fi

RESULT=""
case "$TARGET" in
    stdin)
        RESULT="$(run_node_with_watchdog stdin "$SCRIPT")"
        ;;
    path:*)
        RESULT="$(run_node_with_watchdog path "${TARGET#path:}")"
        ;;
esac

printf '%s' "$RESULT" | jq -e . >/dev/null 2>&1 || exit 0

PARSE_ERROR="$(printf '%s' "$RESULT" | jq -r '.parseError // empty')"
[ -n "$PARSE_ERROR" ] && exit 0

# NOTE: `.ok // empty` is a jq trap here — `//` treats a JSON `false` as falsy too, so it would
# collapse "denied" and "field absent" to the same empty string. `has("ok")` + tostring keeps them apart.
OK="$(printf '%s' "$RESULT" | jq -r 'if has("ok") then (.ok | tostring) else "missing" end')"
[ "$OK" = "missing" ] && exit 0

if [ "$OK" != "true" ]; then
    # `violations` is one entry PER PROBLEM, not per call — a call missing both model and effort
    # produces two entries (no-model + no-effort) at the same line/column. Report both numbers
    # honestly rather than mislabel a problem count as a call count (a reader who goes looking
    # for a second call that does not exist wastes a round-trip on exactly the message this gate
    # depends on to be trusted).
    TOTAL="$(printf '%s' "$RESULT" | jq -r '.violations | length')"
    CALLS="$(printf '%s' "$RESULT" | jq -r '.violations | unique_by([.line, .column]) | length')"
    LINES="$(printf '%s' "$RESULT" | jq -r '.violations[:10][] | "line \(.line): \(.kind)"')"
    MORE=""
    if [ "$TOTAL" -gt 10 ] 2>/dev/null; then
        MORE="
...and $((TOTAL - 10)) more"
    fi
    REASON="workflow-tier-gate: $CALLS untiered agent() call(s), $TOTAL problem(s) in this Workflow script.
$LINES$MORE
Required: agent(prompt, {model: 'haiku'|'sonnet'|'opus'|'fable', effort: 'low'|'medium'|'high'|'xhigh'|'max', ...})
Escape hatch: a same-line // tier-exempt: <reason> comment on the call, reason required."
    jq -nc --arg r "$REASON" \
      '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
    exit 0
fi

# WFT-20/21: fan-out warning, warn-only — never deny.
AGENT_CALLS="$(printf '%s' "$RESULT" | jq -r '.agentCalls // 0')"
if [ "$AGENT_CALLS" -gt 25 ] 2>/dev/null; then
    log_tierwarn "projected_agent_calls=$AGENT_CALLS session=$SESSION_ID"
fi

# D-051/D-05X: pre-launch tier-critic escalation. Reached only once the presence check above has
# already passed (OK = "true") — this is a second, independent deny path, not a fallthrough of the
# first: the presence check above denies on *missing* model/effort, this one denies on a
# *declared* opus/fable tier that looks mechanical and/or blows the script's opus/fable budget.
#
# D-051 originally escalated via permissionDecision:"ask". Live-tested with two real Workflow
# launches on 2026-08-08 (D-05X): this environment's `permissions.defaultMode:"auto"` silently
# auto-resolved the "ask" both times — zero pause, zero visible interrupt, the flagged call ran to
# completion with nothing but a log line to show for it. `ask` is not a channel this gate can rely
# on. Switched to "deny" with its own escape hatch (`// tier-preflight-exempt: <reason>`, distinct
# from the presence check's `tier-exempt` — see tier-scan.js's parsePreflightExemptReason) because
# a real deny cannot be silently auto-approved by auto-mode the way ask can; it forces the driving
# session to fix the tier, get it critiqued, or justify it inline before the launch proceeds.
#
# Runs the same detector's --preflight mode over the same TARGET already resolved above (stdin
# script or a file path) to compute two independent, deterministic, AST-only signals: a
# shape-mismatch heuristic per opus/fable-declared call, and a script-wide opus/fable budget
# ceiling (see tier-scan.js for both). Any failure here — malformed JSON, a parse error, a
# missing detector output — fails open silently, same WFT-16 convention as the rest of this hook:
# a broken preflight step must never block a launch the presence check already allowed.
PREFLIGHT_RESULT=""
case "$TARGET" in
    stdin)
        PREFLIGHT_RESULT="$(run_preflight_with_watchdog stdin "$SCRIPT")"
        ;;
    path:*)
        PREFLIGHT_RESULT="$(run_preflight_with_watchdog path "${TARGET#path:}")"
        ;;
esac
printf '%s' "$PREFLIGHT_RESULT" | jq -e . >/dev/null 2>&1 || PREFLIGHT_RESULT=""

if [ -n "$PREFLIGHT_RESULT" ]; then
    CEILING_EXCEEDED="$(printf '%s' "$PREFLIGHT_RESULT" | jq -r '.ceilingExceeded // false')"
    FLAGGED_CALLS="$(printf '%s' "$PREFLIGHT_RESULT" | jq -c '.calls[]? | select(.flagged == true)')"

    if [ -n "$FLAGGED_CALLS" ]; then
        TIERCRITIC_LOG="${HARNESS_SESS_DIR:-$ROOT/.claude/sessions}/tiercritic.log"
        # One row per already-critiqued callSha (any prior verdict, per D-051: a call is not
        # re-flagged once tier-critic has had its say once, regardless of what it said).
        CRITIQUED_SHAS="$(jq -r '.callSha // empty' "$TIERCRITIC_LOG" 2>/dev/null)" || CRITIQUED_SHAS=""

        NEED_DENY=0
        DENY_LINES=""
        while IFS= read -r CALL; do
            [ -n "$CALL" ] || continue
            CFILE="$(printf '%s' "$CALL" | jq -r '.file')"
            CLINE="$(printf '%s' "$CALL" | jq -r '.line')"
            CSHA="$(printf '%s' "$CALL" | jq -r '.callSha')"
            CMODEL="$(printf '%s' "$CALL" | jq -r '.model')"
            CREASON="$(printf '%s' "$CALL" | jq -r '.reason')"
            CEXEMPT="$(printf '%s' "$CALL" | jq -r '.exempt // false')"

            # D-05X: exemption silences the deny, not the record — a flagged call is tallied to
            # tierpreflight.log unconditionally, whether it ends up denied, exempt, or already
            # critiqued. /routing-audit's section 5 tally depends on seeing all three outcomes.
            log_tierpreflight "tier_preflight_flag=1 file=$CFILE line=$CLINE callSha=$CSHA model=$CMODEL reason=$CREASON exempt=$CEXEMPT ceilingExceeded=$CEILING_EXCEEDED session=$SESSION_ID"

            if [ "$CEXEMPT" = "true" ]; then
                continue
            fi

            if ! printf '%s\n' "$CRITIQUED_SHAS" | grep -qxF "$CSHA"; then
                NEED_DENY=1
                DENY_LINES="$DENY_LINES
- $CFILE:$CLINE declares $CMODEL ($CREASON, callSha=$CSHA)"
            fi
        done <<FLAGGED_EOF
$FLAGGED_CALLS
FLAGGED_EOF

        if [ "$NEED_DENY" -eq 1 ]; then
            REASON="workflow-tier-gate: this Workflow declares opus/fable for stage(s) that look mechanical and/or exceed the opus/fable budget for this script.$DENY_LINES

Before retrying, resolve each flagged call above by ONE of:
  (a) change model/effort to a cheaper tier that actually matches the work, or
  (b) spawn .claude/agents/tier-critic.md via the Task tool on the flagged call(s) (pass its prompt/label/phase and the .assistant/routing.tiers.json rubric it expects), record its verdict to .claude/sessions/tiercritic.log keyed (file,line,callSha) — a callSha already present in that log is never re-flagged, or
  (c) add a same-line // tier-preflight-exempt: <reason> comment on the flagged call if the opus/fable declaration is deliberate and justified, reason required (distinct from // tier-exempt: — that marker answers a different question)."
            jq -nc --arg r "$REASON" \
              '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
            exit 0
        fi
    fi
fi

exit 0
