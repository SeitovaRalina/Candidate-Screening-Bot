#!/usr/bin/env bash
# @spec:REQ-ROUTING-AUDIT
# Entry point for /routing-audit. Thin dispatcher: the actual JSONL/AST work lives in
# audit.py (stdlib-only) and reuses .claude/lib/tier-scan.js for workflow-script coverage
# (WFT-41 — one detector, not two). Default scope is the current project's own transcript
# directory; pass --all-projects for machine-wide aggregation (WFT-40a).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"

command -v python3 >/dev/null 2>&1 || {
    echo "routing-audit: python3 not found on PATH — cannot run." >&2
    exit 1
}

exec python3 "$SCRIPT_DIR/audit.py" --repo-root "$REPO_ROOT" --cwd "$PWD" "$@"
