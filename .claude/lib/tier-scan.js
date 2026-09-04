#!/usr/bin/env node
// @spec:REQ-WORKFLOW-TIER
//
// Shared detector for per-stage model/effort tiering in Workflow scripts (WFT-10..18c).
// Zero dependencies beyond the two vendored files in this directory (acorn 8.17.0, acorn-walk
// 8.3.5 — see VENDOR.md). Runs on plain `node`, no npm install, no build step.
//
// Usage:
//   node tier-scan.js --stdin < script.js
//   node tier-scan.js path/to/a.js path/to/b.js
//   node tier-scan.js --self-test tests/fixtures/workflow
//   node tier-scan.js --preflight --stdin < script.js   (D-051 pre-launch tier-critic gate)
//
// Always prints one JSON object to stdout (see README below for shape). Exit 0 whenever a
// verdict was produced, even when violations were found — the caller (a PreToolUse hook) decides
// policy from `ok`/`violations`, this tool only observes. Exit 2 only when the detector itself
// could not produce a verdict (unreadable file, syntax error, missing arguments) — the caller
// treats that as fail-open, per WFT-16.

'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const acorn = require('./acorn.js');
const walk = require('./walk.js');

const MODELS = new Set(['haiku', 'sonnet', 'opus', 'fable']);
const EFFORTS = new Set(['low', 'medium', 'high', 'xhigh', 'max']);

// WFT-98 signal extraction (--signals mode only, never on the default/gate path).
const WRITE_CAPABLE_TOOLS = new Set(['Write', 'Edit', 'MultiEdit', 'NotebookEdit', 'Bash']);
// Explore is the one agent type this repo ships with Edit/Write/NotebookEdit excluded
// (.claude/agents/Explore.md); every other named agentType includes them. Absent a live
// registry read, this is the only agentType literal decidable without guessing.
const READ_ONLY_AGENT_TYPES = new Set(['explore']);

const PARSE_OPTIONS = {
  ecmaVersion: 'latest',
  sourceType: 'module',
  allowAwaitOutsideFunction: true,
  locations: true,
};

// --- core scan -------------------------------------------------------------

function findProp(properties, name) {
  for (const p of properties) {
    if (p.type !== 'Property') continue;
    const key = p.key;
    if (!p.computed) {
      if ((key.type === 'Identifier' && key.name === name) ||
          (key.type === 'Literal' && key.value === name)) {
        return { node: p, computed: false };
      }
    } else if (key.type === 'Literal' && key.value === name) {
      // computed key that is statically resolvable to 'model'/'effort' — still undecidable
      // per WFT-13 ("model/effort is a computed key ... -> undecidable"), fail closed anyway.
      return { node: p, computed: true };
    }
  }
  return null;
}

function snippetOf(source, node) {
  const raw = source.slice(node.start, Math.min(node.end, node.start + 60));
  const oneLine = raw.split('\n')[0];
  const truncated = oneLine.length < node.end - node.start || raw.includes('\n');
  return truncated ? oneLine + '...' : oneLine;
}

function commentCovers(call, comment) {
  // A `// tier-exempt:` comment associates with a call when it falls on any source line the
  // call's own range spans, including the line the call's closing paren is on. This is a
  // line-based containment rather than a strict char-offset range: a strict [start,end) char
  // check fails the spec's own AC-4 example (`agent(p, {...}) // tier-exempt: ...` — the
  // trailing comment sits just after the call's closing paren, outside [start,end) in raw
  // offsets), while line containment satisfies both that example and a comment nested inside a
  // multi-line call's argument list.
  return comment.loc.start.line >= call.loc.start.line &&
    comment.loc.start.line <= call.loc.end.line;
}

function parseExemptReason(commentValue) {
  const m = /^\s*tier-exempt:\s*(.*)$/.exec(commentValue);
  if (!m) return null;
  const reason = m[1].trim();
  return reason.length > 0 ? reason : '';
}

// D-05X: a distinct marker from `tier-exempt` above, deliberately — that one clears the presence
// gate's "no model/effort at all" violation ("I know this call has no schema, that's intentional");
// this one clears the preflight gate's "declares opus/fable for what looks mechanical" flag ("I
// know this declares opus/fable, that's intentional, here's why"). Different claims, so they get
// different markers rather than one comment doing double duty — conflating them would let a
// presence-gate exemption silently also suppress a preflight concern the author never looked at.
// Same bare-reason-does-not-count convention as parseExemptReason (mirrors the presence check).
function parsePreflightExemptReason(commentValue) {
  const m = /^\s*tier-preflight-exempt:\s*(.*)$/.exec(commentValue);
  if (!m) return null;
  const reason = m[1].trim();
  return reason.length > 0 ? reason : '';
}

// Persisted Workflow-tool scripts are executed as an async function body, not as an ES module:
// every real-corpus sample (180/180) carries both a leading `export const meta = {...}` and a
// trailing top-level `return ...`, and bare `return` is a SyntaxError outside a function under
// any standard JS grammar (sourceType 'module' or 'script'). Parse as a module first — this
// covers plain scripts and every hand-written fixture — and only fall back to the async-function
// wrap when that fails, so the fallback's line-number bookkeeping never taxes the common path.
function parseFlexible(source) {
  try {
    const comments = [];
    const ast = acorn.parse(source, Object.assign({ onComment: comments }, PARSE_OPTIONS));
    return { ast, comments, lineOffset: 0, text: source };
  } catch (moduleErr) {
    // `export` is only legal at module top level, so it must be neutralized before the source
    // can be parsed as a function body. Replace the keyword with equal-length spaces to leave
    // every column position on that line unchanged.
    const stripped = source.replace(/^(\s*)export(\s+)/gm, (m, ws1, ws2) => ws1 + ' '.repeat('export'.length) + ws2);
    const wrapped = '(async function(){\n' + stripped + '\n});';
    try {
      const comments = [];
      const wrappedOptions = Object.assign({ onComment: comments }, PARSE_OPTIONS, { sourceType: 'script' });
      const ast = acorn.parse(wrapped, wrappedOptions);
      // Wrapping prepends exactly one line, so every reported line shifts by +1; callers must
      // subtract `lineOffset` back out before this is meaningful to a human reading the original file.
      return { ast, comments, lineOffset: 1, text: wrapped };
    } catch (wrapErr) {
      throw new Error(`${moduleErr.message} (also failed as async-function body: ${wrapErr.message})`);
    }
  }
}

// Scans one already-read source string. Returns { agentCalls, violations, exemptions }.
// Throws on a genuine parse error — caller decides how to report that.
function scanSource(source, file) {
  const { ast, comments, lineOffset, text } = parseFlexible(source);

  const agentCalls = [];
  walk.simple(ast, {
    CallExpression(node) {
      if (node.callee.type === 'Identifier' && node.callee.name === 'agent') {
        agentCalls.push(node);
      }
    },
  });

  const violations = [];
  const exemptions = [];

  for (const call of agentCalls) {
    const callViolations = [];
    const optsArg = call.arguments[1];

    if (!optsArg || optsArg.type !== 'ObjectExpression') {
      callViolations.push('no-opts');
    } else {
      const properties = optsArg.properties;
      const hasSpread = properties.some((p) => p.type === 'SpreadElement');
      const modelMatch = findProp(properties, 'model');
      const effortMatch = findProp(properties, 'effort');

      const modelUndecidable = !!modelMatch &&
        (modelMatch.computed || modelMatch.node.value.type !== 'Literal');
      const effortUndecidable = !!effortMatch &&
        (effortMatch.computed || effortMatch.node.value.type !== 'Literal');

      if (hasSpread || modelUndecidable || effortUndecidable) {
        callViolations.push('undecidable');
      } else {
        // Kept distinct from each other (WFT-11): `no-model` means the key is absent, so the
        // author never engaged with tiering at all; `invalid-model` means a literal value was
        // written but it is not one of the four allowed aliases (typo, full model id, made-up
        // tier). Both deny — the gate's allow/deny semantics do not change — but only the split
        // makes "58 calls carry a model: key, 53 of them valid" reproducible from this tool's
        // own output instead of a second, undocumented parser.
        if (!modelMatch) {
          callViolations.push('no-model');
        } else if (typeof modelMatch.node.value.value !== 'string' ||
            !MODELS.has(modelMatch.node.value.value)) {
          callViolations.push('invalid-model');
        }
        if (!effortMatch) {
          callViolations.push('no-effort');
        } else if (typeof effortMatch.node.value.value !== 'string' ||
            !EFFORTS.has(effortMatch.node.value.value)) {
          callViolations.push('invalid-effort');
        }
      }
    }

    if (callViolations.length === 0) continue;

    // Look for a `// tier-exempt: <reason>` comment associated with this call.
    let exemptReason = null;
    for (const c of comments) {
      if (c.type !== 'Line' && c.type !== 'Block') continue;
      const parsed = parseExemptReason(c.value);
      if (parsed === null) continue;
      if (!commentCovers(call, c)) continue;
      if (parsed === '') continue; // bare `// tier-exempt:` with no reason does not clear
      exemptReason = parsed;
      break;
    }

    if (exemptReason !== null) {
      exemptions.push({ file, line: call.loc.start.line - lineOffset, reason: exemptReason });
      continue;
    }

    for (const kind of callViolations) {
      violations.push({
        file,
        line: call.loc.start.line - lineOffset,
        column: call.loc.start.column + 1,
        kind,
        snippet: snippetOf(text, call),
      });
    }
  }

  return { agentCalls: agentCalls.length, violations, exemptions };
}

// --- WFT-98 signal extraction (--signals mode) ------------------------------

// Phase markers are collected script-wide rather than restricted to strict Program-level
// statements: every real-corpus script calls `phase('...')` as its own bare statement
// (never nested inside another expression), so a full-tree scan finds the same markers a
// stricter Program.body walk would, without needing to special-case the async-function-body
// wrapper shape from parseFlexible's fallback branch.
function collectPhaseMarkers(ast) {
  const markers = [];
  walk.simple(ast, {
    CallExpression(node) {
      if (node.callee.type === 'Identifier' && node.callee.name === 'phase' &&
          node.arguments.length > 0 && node.arguments[0].type === 'Literal' &&
          typeof node.arguments[0].value === 'string') {
        markers.push({ pos: node.start, value: node.arguments[0].value });
      }
    },
  });
  markers.sort((a, b) => a.pos - b.pos);
  return markers;
}

function nearestPhase(pos, markers) {
  let result = null;
  for (const m of markers) {
    if (m.pos < pos) result = m.value;
    else break;
  }
  return result;
}

function resolveLabel(optsArg) {
  if (!optsArg || optsArg.type !== 'ObjectExpression') {
    return { label: null, labelPrefix: null, labelStatic: true };
  }
  const match = findProp(optsArg.properties, 'label');
  if (!match || match.computed) {
    return { label: null, labelPrefix: null, labelStatic: !match };
  }
  const value = match.node.value;
  if (value.type === 'Literal' && typeof value.value === 'string') {
    return { label: value.value, labelPrefix: null, labelStatic: true };
  }
  if (value.type === 'TemplateLiteral') {
    const prefix = value.quasis.length > 0 ? value.quasis[0].value.cooked : '';
    if (value.expressions.length === 0) {
      return { label: prefix, labelPrefix: null, labelStatic: true };
    }
    return { label: null, labelPrefix: prefix, labelStatic: false };
  }
  return { label: null, labelPrefix: null, labelStatic: false };
}

function resolvePhaseFromOptions(optsArg) {
  if (!optsArg || optsArg.type !== 'ObjectExpression') return { present: false };
  const match = findProp(optsArg.properties, 'phase');
  if (!match) return { present: false };
  if (!match.computed && match.node.value.type === 'Literal' &&
      typeof match.node.value.value === 'string') {
    return { present: true, value: match.node.value.value };
  }
  return { present: true, value: null };
}

function resolveLiteralString(optsArg, name) {
  if (!optsArg || optsArg.type !== 'ObjectExpression') return null;
  const match = findProp(optsArg.properties, name);
  if (!match || match.computed) return null;
  const value = match.node.value;
  return value.type === 'Literal' && typeof value.value === 'string' ? value.value : null;
}

function hasProp(optsArg, name) {
  if (!optsArg || optsArg.type !== 'ObjectExpression') return false;
  return !!findProp(optsArg.properties, name);
}

function resolveWriteToolReachable(optsArg) {
  if (!optsArg || optsArg.type !== 'ObjectExpression') return 'unknown';
  const toolsMatch = findProp(optsArg.properties, 'tools');
  if (toolsMatch && !toolsMatch.computed) {
    const value = toolsMatch.node.value;
    if (value.type === 'ArrayExpression' &&
        value.elements.every((el) => el && el.type === 'Literal' && typeof el.value === 'string')) {
      return value.elements.some((el) => WRITE_CAPABLE_TOOLS.has(el.value));
    }
    return 'unknown';
  }
  const agentTypeMatch = findProp(optsArg.properties, 'agentType');
  if (agentTypeMatch && !agentTypeMatch.computed) {
    const value = agentTypeMatch.node.value;
    if (value.type === 'Literal' && typeof value.value === 'string') {
      return !READ_ONLY_AGENT_TYPES.has(value.value.toLowerCase());
    }
  }
  return 'unknown';
}

// The one decidable shape from WFT-93/98: `const x = await agent(...)` outside a
// parallel()/pipeline() thunk. `ancestors` is the stack acorn-walk's `ancestor` walker
// hands back at the `agent()` CallExpression, so the three nodes above it on that stack are
// exactly AwaitExpression -> VariableDeclarator -> VariableDeclaration when the pattern holds.
function boundConstName(call, ancestors) {
  const n = ancestors.length;
  if (n < 4 || ancestors[n - 1] !== call) return null;
  const awaitNode = ancestors[n - 2];
  if (!awaitNode || awaitNode.type !== 'AwaitExpression' || awaitNode.argument !== call) return null;
  const declarator = ancestors[n - 3];
  if (!declarator || declarator.type !== 'VariableDeclarator' || declarator.init !== awaitNode) return null;
  if (!declarator.id || declarator.id.type !== 'Identifier') return null;
  const declaration = ancestors[n - 4];
  if (!declaration || declaration.type !== 'VariableDeclaration' || declaration.kind !== 'const') return null;
  return declarator.id.name;
}

// Deliberately name-based, not scope-aware: it will also match `name` used as a property key
// or member-expression property elsewhere in the subtree. That over-approximation is the
// price of staying a single AST pass; WFT-98 asks for one decidable hop, not a resolver.
function subtreeReferencesIdentifier(node, name) {
  let found = false;
  walk.simple(node, {
    Identifier(n) {
      if (n.name === name) found = true;
    },
  });
  return found;
}

function resolveFeedsJudgment(call, ancestors, insideThunk, agentCallInfos) {
  if (insideThunk) return 'unknown';
  const varName = boundConstName(call, ancestors);
  if (!varName) return 'unknown';
  for (const other of agentCallInfos) {
    if (other.node === call || other.node.start <= call.end) continue;
    const promptArg = other.node.arguments[0];
    if (promptArg && subtreeReferencesIdentifier(promptArg, varName)) return true;
  }
  return false;
}

// Scans one already-read source string for WFT-98 signals. Throws on a genuine parse error,
// same contract as scanSource.
function scanSignals(source, file) {
  const { ast, lineOffset, text } = parseFlexible(source);
  const phaseMarkers = collectPhaseMarkers(ast);

  const agentCallInfos = [];
  walk.ancestor(ast, {
    CallExpression(node, state, ancestors) {
      if (node.callee.type === 'Identifier' && node.callee.name === 'agent') {
        agentCallInfos.push({ node, ancestors: ancestors.slice() });
      }
    },
  });

  return agentCallInfos.map(({ node: call, ancestors }) => {
    const optsArg = call.arguments[1];
    const promptArg = call.arguments[0];

    const insideThunk = ancestors.some((a) => a !== call && a.type === 'CallExpression' &&
      a.callee && a.callee.type === 'Identifier' && (a.callee.name === 'parallel' || a.callee.name === 'pipeline'));

    const labelInfo = resolveLabel(optsArg);
    const phaseFromOpts = resolvePhaseFromOptions(optsArg);
    const phase = phaseFromOpts.present ? phaseFromOpts.value : nearestPhase(call.start, phaseMarkers);
    const callText = text.slice(call.start, call.end);

    return {
      file,
      line: call.loc.start.line - lineOffset,
      callSha: crypto.createHash('sha256').update(callText).digest('hex').slice(0, 12),
      label: labelInfo.label,
      labelPrefix: labelInfo.labelPrefix,
      labelStatic: labelInfo.labelStatic,
      phase,
      model: resolveLiteralString(optsArg, 'model'),
      effort: resolveLiteralString(optsArg, 'effort'),
      schema: hasProp(optsArg, 'schema'),
      writeToolReachable: resolveWriteToolReachable(optsArg),
      feedsJudgment: resolveFeedsJudgment(call, ancestors, insideThunk, agentCallInfos),
      prompt: promptArg ? text.slice(promptArg.start, promptArg.end).slice(0, 400) : null,
    };
  });
}

// --- D-051 preflight signals (--preflight mode) -----------------------------
//
// Pre-launch heuristic for the tier-critic escalation gate (REQ-WORKFLOW-TIER-GATE, D-051).
// A sibling of --signals: a separate output shape that never touches the ok/violations/
// exemptions object the presence gate (scanSource, above) depends on. Two independent,
// deterministic, AST-only signals — nothing here calls a model:
//
//   1. Shape-mismatch: an opus/fable-declared call whose own AST shape reads as mechanical
//      (schema: true, i.e. expects structured output; writeToolReachable: false, i.e. a
//      literal read-only tools:/agentType:) and whose label/phase/prompt-prefix carries no
//      judgment-shaped keyword. A hit means "declared frontier-tier, looks mechanical" — never
//      proof, just a candidate for a human (via tier-critic) to look at.
//   2. Budget ceiling: opus/fable share of all agent() calls in the script, independent of #1
//      — catches "everything is opus" even when no individual stage trips the shape heuristic.

// Mirrors JUDGMENT_KEYWORDS in .claude/skills/routing-audit/scripts/audit.py (WFT-99) —
// duplicated across the JS/Python boundary by hand, same as this repo's other first-party
// cross-language constants (see VENDOR.md's tier-scan.js note). Update both together.
const JUDGMENT_KEYWORDS_PREFLIGHT = [
  'audit', 'review', 'critic', 'skeptic', 'judge', 'verify', 'adversar', 'plan',
  'проверк', 'ревью', 'критик', 'скептик', 'аудит', 'план',
];

// Unlike audit.py's classify_judgment (WFT-99, label/labelPrefix/phase ONLY — reading the full
// prompt body measured 69% false-positive on harness boilerplate), this checks a short PREFIX
// of the authored prompt too, by design (D-051): the preflight gate only ever produces a
// non-blocking `ask`, never a deny, so the cost of a false negative here is far lower than the
// cost that drove WFT-99's restriction on the deny-capable presence gate.
const PROMPT_PREFIX_CHARS = 200;

function promptPrefixMatchesJudgment(label, labelPrefix, phase, promptPrefix) {
  const fields = [label, labelPrefix, phase, promptPrefix];
  for (const value of fields) {
    if (!value) continue;
    const low = value.toLowerCase();
    for (const kw of JUDGMENT_KEYWORDS_PREFLIGHT) {
      if (low.includes(kw)) return kw;
    }
  }
  return null;
}

// Absolute count and ratio thresholds for the opus/fable budget ceiling (D-051). Chosen
// against this repo's own established fan-out precedent (WFT-20/21 already warns at >25 total
// agent() calls in one script) rather than an invented number:
//   - PREFLIGHT_CEILING_ABS = 8: roughly a third of the existing 25-call fan-out ceiling.
//     Running that many stages at opus/fable in one script is excessive in absolute cost even
//     when it is a minority share of a large, legitimately fanned-out workflow.
//   - PREFLIGHT_CEILING_RATIO = 0.5 with PREFLIGHT_CEILING_RATIO_MIN_CALLS = 4: "opus is the
//     default" for the majority of stages, gated on a minimum script size so a legitimate small
//     script (e.g. 2 stages, 1 of them a real judgment call) does not sit at 50% and false-flag.
const PREFLIGHT_CEILING_ABS = 8;
const PREFLIGHT_CEILING_RATIO = 0.5;
const PREFLIGHT_CEILING_RATIO_MIN_CALLS = 4;

// Scans one source string for preflight signals. Only agent() calls with a literal
// model:'opus'|'fable' are returned in `calls` — WFT-97's own precedent (the packet only ever
// considers opus/fable) applies here too: there is nothing to flag on a call already declaring
// a cheap tier. Throws on a genuine parse error, same contract as scanSource/scanSignals.
function scanPreflight(source, file) {
  const { ast, comments, lineOffset, text } = parseFlexible(source);
  const phaseMarkers = collectPhaseMarkers(ast);

  const agentCallNodes = [];
  walk.simple(ast, {
    CallExpression(node) {
      if (node.callee.type === 'Identifier' && node.callee.name === 'agent') {
        agentCallNodes.push(node);
      }
    },
  });

  const calls = [];
  let opusFableCount = 0;

  for (const call of agentCallNodes) {
    const optsArg = call.arguments[1];
    const promptArg = call.arguments[0];
    const model = resolveLiteralString(optsArg, 'model');
    if (model !== 'opus' && model !== 'fable') continue;
    opusFableCount++;

    const labelInfo = resolveLabel(optsArg);
    const phaseFromOpts = resolvePhaseFromOptions(optsArg);
    const phase = phaseFromOpts.present ? phaseFromOpts.value : nearestPhase(call.start, phaseMarkers);
    const schema = hasProp(optsArg, 'schema');
    const writeToolReachable = resolveWriteToolReachable(optsArg);
    const promptPrefix = promptArg
      ? text.slice(promptArg.start, Math.min(promptArg.end, promptArg.start + PROMPT_PREFIX_CHARS)).toLowerCase()
      : null;
    const matchedKeyword = promptPrefixMatchesJudgment(labelInfo.label, labelInfo.labelPrefix, phase, promptPrefix);
    const shapeMismatch = schema === true && writeToolReachable === false && matchedKeyword === null;
    const callText = text.slice(call.start, call.end);

    // Look for a `// tier-preflight-exempt: <reason>` comment associated with this call — same
    // line-containment rule as the presence gate's `tier-exempt` (commentCovers), deliberately a
    // different marker (see parsePreflightExemptReason).
    let exempt = false;
    let exemptReason = null;
    for (const c of comments) {
      if (c.type !== 'Line' && c.type !== 'Block') continue;
      const parsed = parsePreflightExemptReason(c.value);
      if (parsed === null) continue;
      if (!commentCovers(call, c)) continue;
      if (parsed === '') continue; // bare `// tier-preflight-exempt:` with no reason does not clear
      exempt = true;
      exemptReason = parsed;
      break;
    }

    calls.push({
      file,
      line: call.loc.start.line - lineOffset,
      callSha: crypto.createHash('sha256').update(callText).digest('hex').slice(0, 12),
      model,
      schema,
      writeToolReachable,
      label: labelInfo.label,
      labelPrefix: labelInfo.labelPrefix,
      phase,
      shapeMismatch,
      matchedKeyword,
      exempt,
      exemptReason,
    });
  }

  return { agentCallsTotal: agentCallNodes.length, opusFableCount, calls };
}

// Finalizes a (possibly multi-file-merged) preflight scan into the printed shape: computes the
// budget ceiling over the merged totals and stamps `flagged`/`reason` on every call — a call is
// flagged either because it individually shape-mismatches, or because the whole script blew the
// ceiling (in which case every opus/fable call in scope is a candidate, per D-051: the ceiling
// signal is script-wide, not per-call, so there is no single "guilty" call to isolate).
function finalizePreflight(merged, hasError) {
  const ceilingExceeded = !hasError && (
    merged.opusFableCount > PREFLIGHT_CEILING_ABS ||
    (merged.agentCallsTotal >= PREFLIGHT_CEILING_RATIO_MIN_CALLS && merged.agentCallsTotal > 0 &&
      (merged.opusFableCount / merged.agentCallsTotal) > PREFLIGHT_CEILING_RATIO)
  );
  const calls = merged.calls.map((c) => {
    const flagged = c.shapeMismatch || ceilingExceeded;
    let reason = null;
    if (flagged) {
      reason = c.shapeMismatch && ceilingExceeded ? 'shape-mismatch+ceiling'
        : c.shapeMismatch ? 'shape-mismatch' : 'ceiling';
    }
    return Object.assign({}, c, { flagged, reason });
  });
  return {
    ok: !hasError,
    agentCallsTotal: merged.agentCallsTotal,
    opusFableCount: merged.opusFableCount,
    ceilingExceeded,
    ceilingThreshold: {
      abs: PREFLIGHT_CEILING_ABS,
      ratio: PREFLIGHT_CEILING_RATIO,
      ratioMinCalls: PREFLIGHT_CEILING_RATIO_MIN_CALLS,
    },
    calls,
    parseError: merged.parseError,
  };
}

function runPreflightFiles(files) {
  const merged = { agentCallsTotal: 0, opusFableCount: 0, calls: [], parseError: null };
  const errors = [];
  for (const file of files) {
    let source;
    try {
      source = fs.readFileSync(file, 'utf8');
    } catch (err) {
      errors.push(`${file}: ${err.message}`);
      continue;
    }
    try {
      const scanned = scanPreflight(source, file);
      merged.agentCallsTotal += scanned.agentCallsTotal;
      merged.opusFableCount += scanned.opusFableCount;
      merged.calls.push(...scanned.calls);
    } catch (err) {
      errors.push(`${file}: ${err.message}`);
    }
  }
  if (errors.length > 0) {
    merged.parseError = errors.join('; ');
    return finalizePreflight(merged, true);
  }
  return finalizePreflight(merged, false);
}

function runPreflightStdin() {
  let source;
  try {
    source = readStdin();
  } catch (err) {
    return finalizePreflight(
      { agentCallsTotal: 0, opusFableCount: 0, calls: [], parseError: `<stdin>: ${err.message}` }, true
    );
  }
  try {
    const scanned = scanPreflight(source, '<stdin>');
    return finalizePreflight(
      { agentCallsTotal: scanned.agentCallsTotal, opusFableCount: scanned.opusFableCount, calls: scanned.calls, parseError: null },
      false
    );
  } catch (err) {
    return finalizePreflight(
      { agentCallsTotal: 0, opusFableCount: 0, calls: [], parseError: `<stdin>: ${err.message}` }, true
    );
  }
}

// --- CLI ---------------------------------------------------------------------

function readStdin() {
  return fs.readFileSync(0, 'utf8');
}

function runFiles(files) {
  const result = { ok: true, agentCalls: 0, violations: [], exemptions: [], parseError: null };
  const errors = [];

  for (const file of files) {
    let source;
    try {
      source = fs.readFileSync(file, 'utf8');
    } catch (err) {
      errors.push(`${file}: ${err.message}`);
      continue;
    }
    try {
      const scanned = scanSource(source, file);
      result.agentCalls += scanned.agentCalls;
      result.violations.push(...scanned.violations);
      result.exemptions.push(...scanned.exemptions);
    } catch (err) {
      errors.push(`${file}: ${err.message}`);
    }
  }

  if (errors.length > 0) {
    result.ok = false;
    result.parseError = errors.join('; ');
    return { result, exitCode: 2 };
  }

  result.ok = result.violations.length === 0;
  return { result, exitCode: 0 };
}

function runStdin() {
  let source;
  try {
    source = readStdin();
  } catch (err) {
    return {
      result: { ok: false, agentCalls: 0, violations: [], exemptions: [], parseError: `<stdin>: ${err.message}` },
      exitCode: 2,
    };
  }
  try {
    const scanned = scanSource(source, '<stdin>');
    return {
      result: {
        ok: scanned.violations.length === 0,
        agentCalls: scanned.agentCalls,
        violations: scanned.violations,
        exemptions: scanned.exemptions,
        parseError: null,
      },
      exitCode: 0,
    };
  } catch (err) {
    return {
      result: { ok: false, agentCalls: 0, violations: [], exemptions: [], parseError: `<stdin>: ${err.message}` },
      exitCode: 2,
    };
  }
}

function deepEqual(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}

function runSelfTest(dir) {
  const entries = fs.readdirSync(dir).filter((f) => f.endsWith('.js'));
  entries.sort();
  let failures = 0;

  for (const entry of entries) {
    const jsPath = path.join(dir, entry);
    const expectedPath = path.join(dir, entry.replace(/\.js$/, '.expected.json'));
    if (!fs.existsSync(expectedPath)) {
      console.log(`SKIP ${entry} (no sibling .expected.json)`);
      continue;
    }
    const expected = JSON.parse(fs.readFileSync(expectedPath, 'utf8'));

    let actual;
    const source = fs.readFileSync(jsPath, 'utf8');
    try {
      const scanned = scanSource(source, entry);
      actual = {
        ok: scanned.violations.length === 0,
        agentCalls: scanned.agentCalls,
        violations: scanned.violations,
        exemptions: scanned.exemptions,
        parseError: null,
      };
    } catch (err) {
      actual = { ok: false, agentCalls: 0, violations: [], exemptions: [], parseError: `${entry}: ${err.message}` };
    }

    if (deepEqual(actual, expected)) {
      console.log(`PASS ${entry}`);
    } else {
      failures++;
      console.log(`FAIL ${entry}`);
      console.log(`  expected: ${JSON.stringify(expected)}`);
      console.log(`  actual:   ${JSON.stringify(actual)}`);
    }
  }

  console.log(failures === 0 ? `${entries.length} fixture(s), all passed` : `${failures} of ${entries.length} fixture(s) failed`);
  return failures === 0 ? 0 : 1;
}

// --signals is a separate output mode (WFT-108): it never touches the ok/violations/exemptions
// shape above, so it cannot regress the gate's default output no matter how it evolves.
function runSignalsFiles(files) {
  const records = [];
  for (const file of files) {
    let source;
    try {
      source = fs.readFileSync(file, 'utf8');
    } catch (err) {
      console.error(`${file}: ${err.message}`);
      continue;
    }
    try {
      records.push(...scanSignals(source, file));
    } catch (err) {
      console.error(`${file}: ${err.message}`);
    }
  }
  return records;
}

function runSignalsStdin() {
  let source;
  try {
    source = readStdin();
  } catch (err) {
    console.error(`<stdin>: ${err.message}`);
    return [];
  }
  try {
    return scanSignals(source, '<stdin>');
  } catch (err) {
    console.error(`<stdin>: ${err.message}`);
    return [];
  }
}

function main(argv) {
  if (argv.length === 0) {
    console.log(JSON.stringify({
      ok: false, agentCalls: 0, violations: [], exemptions: [],
      parseError: 'usage: tier-scan.js --stdin | <path>... | --self-test <fixture-dir> | --signals [--stdin | <path>...] | --preflight [--stdin | <path>...]',
    }));
    return 2;
  }

  if (argv[0] === '--self-test') {
    const dir = argv[1];
    if (!dir) {
      console.error('--self-test requires a fixture directory argument');
      return 2;
    }
    return runSelfTest(dir);
  }

  if (argv[0] === '--signals') {
    const rest = argv.slice(1);
    const records = rest[0] === '--stdin' ? runSignalsStdin() : runSignalsFiles(rest);
    console.log(JSON.stringify(records));
    return 0;
  }

  if (argv[0] === '--preflight') {
    const rest = argv.slice(1);
    const result = rest[0] === '--stdin' ? runPreflightStdin() : runPreflightFiles(rest);
    console.log(JSON.stringify(result));
    return 0;
  }

  let outcome;
  if (argv[0] === '--stdin') {
    outcome = runStdin();
  } else {
    outcome = runFiles(argv);
  }

  console.log(JSON.stringify(outcome.result));
  return outcome.exitCode;
}

if (require.main === module) {
  // Do not process.exit() right after a large console.log: on a pipe, stdout is not flushed
  // synchronously, so an immediate exit truncates the JSON — silently, since a truncated object
  // can still happen to parse. Setting exitCode and letting the event loop drain naturally lets
  // Node flush the pending write before the process actually exits.
  process.exitCode = main(process.argv.slice(2));
}

module.exports = { scanSource, scanSignals, scanPreflight, MODELS, EFFORTS };
