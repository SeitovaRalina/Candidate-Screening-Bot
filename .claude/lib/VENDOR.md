# Vendored dependencies

Fetched by `curl` from the npm registry tarball, never agent-authored. Bytes are unmodified from
upstream `dist/`. Verify with `shasum -a 256 -c` against the table below before trusting either file
(REQ-WORKFLOW-TIER WFT-18).

## acorn

- Package: `acorn`
- Version: `8.17.0` (pinned)
- License: MIT
- Upstream: https://registry.npmjs.org/acorn/-/acorn-8.17.0.tgz
- Vendored file: `dist/acorn.js` (pre-built UMD bundle, zero runtime deps)
- Local path: `.claude/lib/acorn.js`
- Size: 244,682 bytes
- SHA-256: `b373ccd10e9deb63654289f73216eeefcaf0405d9ee24289aabf596b91b4c318`
- Fetched: 2026-07-25

## acorn-walk

- Package: `acorn-walk`
- Version: `8.3.5` (pinned)
- License: MIT
- Upstream: https://registry.npmjs.org/acorn-walk/-/acorn-walk-8.3.5.tgz
- Vendored file: `dist/walk.js` (zero runtime `require()`; its acorn dep is type-alignment only)
- Local path: `.claude/lib/walk.js`
- Size: 16,739 bytes
- SHA-256: `1aa9615d8ea06e2126a21a4c21eb7b8b97a69e5eda256f06d2c48834a57cbf0e`
- Fetched: 2026-07-25

## tier-scan.js (first-party, not vendored)

- File: `tier-scan.js` — the harness's own AST-walk detector for `workflow-tier-gate.sh`
  (REQ-WORKFLOW-TIER), built on top of the acorn/walk output above. Not fetched from a
  registry — this one is ours, and is expected to be hand-edited.
- Local path: `.claude/lib/tier-scan.js`
- SHA-256: `421f452939f41fcb10d1c0cd5a165fabdae31eab151c76143e35b30a56d58b76`
- Verified by: `verify_vendor_checksums()` in `.claude/hooks/workflow-tier-gate.sh` (WFT-18),
  the same mechanism as the two vendored files above — a mismatch fails the gate OPEN, and is
  never silent: logged to `.claude/sessions/tierwarn.log` as
  `vendor_checksum_inert=1 cause=checksum-mismatch:.claude/lib/tier-scan.js`.
- Unlike acorn.js/walk.js, legitimate edits to this file ARE expected. After any edit, recompute
  and update the SHA-256 here **in the same commit**: `shasum -a 256 .claude/lib/tier-scan.js`.
  Forgetting to update it does not silently disable the gate for an attacker's tamper — it fails
  OPEN on the very next PreToolUse (WFT-16) and is logged, so a stale entry is a same-session,
  fail-open cost, not a silent hole.

## Verify

```sh
shasum -a 256 -c - <<'EOF'
b373ccd10e9deb63654289f73216eeefcaf0405d9ee24289aabf596b91b4c318  .claude/lib/acorn.js
1aa9615d8ea06e2126a21a4c21eb7b8b97a69e5eda256f06d2c48834a57cbf0e  .claude/lib/walk.js
421f452939f41fcb10d1c0cd5a165fabdae31eab151c76143e35b30a56d58b76  .claude/lib/tier-scan.js
EOF
```

## Do not

- Do not hand-edit `acorn.js` or `walk.js`. Re-fetch a pinned version instead.
- Do not bump versions without re-verifying license (MIT) and re-recording the SHA-256 here.
- Do not edit `tier-scan.js` without updating its SHA-256 above in the same commit.

## Security history

One advisory ever against acorn: GHSA-6chw-6frg-f759 (ReDoS, CVSS 7.5), affects `<5.7.4 / <6.4.1 /
<7.1.1`. The 8.x line vendored here is unaffected.
