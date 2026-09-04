#!/usr/bin/env bash
# SessionStart hook — inject project state into agent context.
# Budget: ~3-5K tokens. Stays silent if files missing.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

echo "<effective-harness-state>"
echo ""

# 0) MODE — surfaced first: governs whether spec/trace/evidence gates block or advise.
#    @spec:REQ-MODE
MODE_FILE="$ROOT/.assistant/mode.json"
MODE="advisory"
if [ -f "$MODE_FILE" ] && command -v jq >/dev/null 2>&1; then
    MODE="$(jq -r '.mode // "advisory"' "$MODE_FILE" 2>/dev/null || echo advisory)"
fi
echo "=== MODE: $MODE ==="
if [ "$MODE" = "production" ]; then
    echo "Production mode. spec-gate / trace-gate / review-gate BLOCK: a clean spec is required before editing harness source; every approved requirement needs a @spec: anchor; done requires a passed review + external evidence."
elif [ "$MODE" = "prototype" ]; then
    echo "Prototype mode. Mode-aware gates (spec-gate/trace-gate/review-gate) advise, they do not block — fast iteration. Always-on gates (self-config-guard.sh, workflow-tier-gate.sh) still block regardless of mode. mode-gate keeps output in the sandbox (writes to production source are blocked). Promote via /elicit -> spec -> review, or set .assistant/mode.json {\"mode\":\"production\"}."
else
    echo "Advisory mode (no mode.json). Mode-aware gates (spec-gate/trace-gate/review-gate) advise, nothing blocks there, no sandbox. Always-on gates (self-config-guard.sh, workflow-tier-gate.sh) still block regardless of mode. Set .assistant/mode.json to {\"mode\":\"prototype\"} or {\"mode\":\"production\"} to activate the mode-aware gates."
fi
echo ""

# 0a) workflow-tier-gate activation state (WFT-15b) — printed unconditionally, one greppable
#     line, so a fail-open (WFT-16) is never a silent no-op the way D-047's doctrine-only rule was.
#     Precedence: disabled -> node missing -> detector missing -> not registered -> vendor
#     integrity (WFT-18) — no point hashing when the gate is already off or the detector absent.
#     The integrity check mirrors workflow-tier-gate.sh's own verify_vendor_checksums(): same
#     source of truth (.claude/lib/VENDOR.md's `## Verify` shasum -c table, never hardcoded
#     hex here), same cause strings, so the banner and the gate's tierwarn.log stay consistent.
tier_gate_state() {
    if [ "${HARNESS_TIER_GATE:-on}" = "off" ]; then
        echo "INERT: disabled by HARNESS_TIER_GATE"; return
    fi
    if ! command -v node >/dev/null 2>&1; then
        echo "INERT: node not found"; return
    fi
    if [ ! -f "$ROOT/.claude/lib/tier-scan.js" ]; then
        echo "INERT: detector missing"; return
    fi
    local registered=0 settings="$ROOT/.claude/settings.json"
    if [ -f "$settings" ]; then
        if command -v jq >/dev/null 2>&1; then
            if jq -e '.hooks.PreToolUse[]? | select((.matcher // "") | test("Workflow"))' \
                "$settings" >/dev/null 2>&1; then
                registered=1
            fi
        elif grep -Eq '"matcher"[[:space:]]*:[[:space:]]*"[^"]*Workflow' "$settings" 2>/dev/null; then
            registered=1
        fi
    fi
    if [ "$registered" -ne 1 ]; then
        echo "INERT: not registered"; return
    fi

    local vendor_md table line expected file actual
    vendor_md="$ROOT/.claude/lib/VENDOR.md"
    if [ ! -f "$vendor_md" ]; then
        echo "INERT: vendor-doc-unreadable"; return
    fi
    if ! command -v shasum >/dev/null 2>&1; then
        echo "INERT: shasum-unavailable"; return
    fi
    # Same regex the gate uses to lift the `<hex>  <path>` lines straight out of the
    # `## Verify` fenced block (already in shasum -c's own input format).
    table="$(grep -E '^[0-9a-f]{64}  \.claude/lib/[A-Za-z0-9_.-]+\.js$' "$vendor_md" 2>/dev/null)" || true
    if [ -z "$table" ]; then
        echo "INERT: vendor-doc-unreadable"; return
    fi
    while IFS= read -r line; do
        [ -n "$line" ] || continue
        expected="${line%%  *}"
        file="${line#*  }"
        if [ ! -f "$ROOT/$file" ]; then
            echo "INERT: checksum-mismatch:$file"; return
        fi
        actual="$(shasum -a 256 "$ROOT/$file" 2>/dev/null | awk '{print $1}')" || true
        if [ "$actual" != "$expected" ]; then
            echo "INERT: checksum-mismatch:$file"; return
        fi
    done <<TABLE_EOF
$table
TABLE_EOF

    echo "ACTIVE"
}
echo "workflow-tier-gate: $(tier_gate_state)"
echo ""

# 0b) Stage->tier routing table (WFT-64) — data lives in .assistant/routing.tiers.json, owned by
#     the orchestrator. Inject nothing when absent; never hardcode the table here (WFT-60a).
ROUTING_FILE="$ROOT/.assistant/routing.tiers.json"
if [ -f "$ROUTING_FILE" ] && command -v jq >/dev/null 2>&1; then
    ROWS="$(jq -r '.rows[]? | "\(.stage): \(.model)/\(.effort)"' "$ROUTING_FILE" 2>/dev/null | head -5)"
    if [ -n "$ROWS" ]; then
        echo "=== ROUTING TIERS (.assistant/routing.tiers.json) ==="
        printf '%s\n' "$ROWS"
        echo ""
    fi
fi

echo "=== SELF-ROUTE ==="
echo "Decide the flow yourself — no orchestrator skill needed. A non-trivial task (multi-file, new behavior, unclear requirements) → start with /elicit to write a spec, then /pre-feature → /implementor → /spec-review. A trivial / mechanical task → do it directly. /pre-feature already decomposes the work into tasks. In production mode the gates enforce this; in prototype mode it is your judgment."
echo ""

# 1) INVARIANTS — load-bearing rules
if [ -f "$ROOT/.assistant/INVARIANTS.md" ]; then
    echo "=== INVARIANTS (hard rules — every subagent must respect) ==="
    cat "$ROOT/.assistant/INVARIANTS.md"
    echo ""
fi

# 2) Last 5 decisions — full blocks (supports `## D-NNN` and `## ADR-N` styles;
#    the `[0-9]` guard skips literal template headers like `## ADR-N: <title>`)
if [ -f "$ROOT/.assistant/decisions.md" ]; then
    echo "=== RECENT DECISIONS (last 5, append-only log) ==="
    awk '
        /^## (D-|ADR-)[0-9]/ { n++; cur=n; blocks[cur]=$0 "\n"; next }
        /^## / && cur>0 { cur=0 }
        cur>0 { blocks[cur]=blocks[cur] $0 "\n" }
        END {
            start=n-N+1; if(start<1) start=1
            for(i=start;i<=n;i++) printf "%s", blocks[i]
        }
    ' N=5 "$ROOT/.assistant/decisions.md" | head -n 150
    echo ""
fi

# 3) Open questions — headers + priority groups (supports `## OQ-NNN` and `### Q<n>`
#    styles; resolved items written as `### ~~Q2 …~~` fall out naturally)
if [ -f "$ROOT/.assistant/open-questions.md" ]; then
    echo "=== OPEN QUESTIONS (unresolved design questions, see file for details) ==="
    { grep -E '^### (OQ-|Q)[0-9]|^## OQ-[0-9]|^## .*[Pp]riority|priority:' "$ROOT/.assistant/open-questions.md" || true; } | head -40
    echo ""
fi

# 4) Memory bank index hint
if [ -f "$ROOT/.memory-bank/index.md" ]; then
    echo "=== MEMORY BANK INDEX (read .memory-bank/index.md for navigation) ==="
    { grep -E '^- \[' "$ROOT/.memory-bank/index.md" || true; } | head -30
    echo ""
fi

# 5) Git status (light)
if command -v git >/dev/null 2>&1 && [ -d "$ROOT/.git" ]; then
    echo "=== GIT STATUS ==="
    git -C "$ROOT" branch --show-current 2>/dev/null || true
    git -C "$ROOT" status --short 2>/dev/null | head -20 || true
    echo ""
    echo "=== RECENT COMMITS ==="
    git -C "$ROOT" log --oneline -5 2>/dev/null || true
    echo ""
fi

echo "</effective-harness-state>"

exit 0
