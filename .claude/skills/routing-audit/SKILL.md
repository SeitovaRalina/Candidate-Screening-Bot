<!-- @harness-owned: true; harness-version: 1.0.0 -->
<!-- @spec:REQ-ROUTING-AUDIT -->
---
name: routing-audit
cadence: weekly
description: Report model/effort tier compliance from local Claude Code transcripts — token share by tier, agent counts, workflow-script coverage, deterministic mis-tier flags, and gate health. Answers "did the tiering fix work?" in measured terms. Use for "routing audit", "tier compliance", "model spend by tier", "аудит роутинга".
allowed-tools: [Bash, Read, Task]
---

# /routing-audit — tier compliance report (WFT-40..44)

Answers "did the per-stage model/effort fix actually change behaviour?" from measured transcript
data, not from doctrine. Companion to the `workflow-tier-gate` hook (`REQ-WORKFLOW-TIER-GATE`):
the gate stops new violations, this skill measures whether violations are actually going down.

## Privacy boundary (WFT-40a, WFT-101, WFT-101a, WFT-101b) — read before running

`~/.claude/projects/**` holds transcripts for **every project on this machine**, and this skill's
output is meant to land in `swarm-report/`, which consuming projects track. So:

- **Default scope is the current project only** — its own `~/.claude/projects/<slug>/` directory.
- **Machine-wide aggregation requires `--all-projects`**, explicitly, every time.
- **Sections 1-6 remain prompt-blind, transcript-sourced.** They read only `message.model`,
  `message.usage` (token counts) and tool_use `name` fields from `agent-*.jsonl`. They never read
  prompt text, tool_input, tool output, or assistant prose, and never print any. If you need to
  double check this, `grep -n 'content\[' scripts/audit.py` should turn up nothing that
  dereferences text content — only `type == "tool_use"` and the `name` key. This recipe stays
  true because of the next point, not despite it.
- **Section 7 (`--critique`) is the one deliberate exception**, and it is scoped narrowly: it
  reads the **current project's own authored `agent()` prompts**, sourced from the AST via
  `.claude/lib/tier-scan.js --signals` — **never** from `agent-*.jsonl`. That is what keeps the
  `content\[` grep above meaningful: the JSONL-reading code path in `audit.py` never touches
  prompt text, in this slice or any other. `--critique` **refuses to combine with
  `--all-projects`** (prints one line and exits 0) precisely because it would otherwise send
  another engagement's authored prompts into a report this repo tracks. It still cannot bound
  content a script *embeds* from elsewhere (e.g. another project's path or prompt text pasted into
  this project's own persisted script) — only the directory scope, not the content within it.
- Section 7's own output is closed-vocabulary (WFT-101a): findings are composed only from signal
  names/values, `label`/`labelPrefix`, `phase`, declared/suggested tier, and the matched
  `routing.tiers.json` row — never prompt text, verbatim or paraphrased. The prompt travels only
  as far as the gitignored packet file (`.claude/sessions/tiercritic-packet.json`), for the
  classifier's own use.

Do not paste this skill's output into a different project's `swarm-report/` without checking it
was run in default (current-project) scope, or you will be copying another engagement's project
names into a repo that shouldn't see them.

## Steps

1. Run `bash ${CLAUDE_SKILL_DIR}/scripts/audit.sh` for the current project, or add
   `--all-projects` for a machine-wide report. `--weeks N` limits the lookback window (useful for
   the machine-wide report, which otherwise scans this machine's full transcript history).
   - Add `--critique` to also emit section 7's signal packet (see step 3). Without it, output is
     byte-identical to a plain run and no model call is made (AC-10). `--critique` refuses to
     combine with `--all-projects` — see the privacy boundary above.
2. Read the six sections in order:
   - **1. Token share by tier** — `input_tokens` / `cache_read_input_tokens` / `output_tokens`
     tier share, per project per ISO week, plus a rolled-up weekly summary. Output tokens alone
     are usually under 1% of counted volume — read all three fields, not just output.
   - **2. Agent counts by tier** — frontier (opus|fable) vs cheap (sonnet|haiku) share of
     subagent instances, per project and total. Tier = the first `message.model` seen in that
     agent's transcript.
   - **3. Workflow-script coverage** — `model:`/`effort:` literal coverage across persisted
     `<session>/workflows/scripts/*.js`, via `.claude/lib/tier-scan.js` (the same AST detector the
     `workflow-tier-gate` hook uses — WFT-41: one detector, not two, so the gate and this report
     cannot disagree). `--weeks N` now scopes this section too (filtered by file mtime): without
     it, section 3 blends every script this machine has ever persisted, pre-gate and post-gate
     alike, and understates current compliance — pass `--weeks` to read a figure that reflects
     gated behaviour.
   - **4. Deterministic mis-tier flags** — frontier-model stages whose tool calls are >50%
     drive/capture (screenshot/tap/swipe/simulator-boot/browser-drive tools) with zero file
     writes. Purely rule-based (WFT-43: no LLM verdicts) — a candidate list to downgrade tier on,
     not an accusation.
   - **5. Gate health** — `// tier-exempt:` count + verbatim reasons, `.claude/sessions/
     tierwarn.log` fan-out warnings. Scoped to the current repo regardless of `--all-projects`
     (exemptions and fan-out are repo-local concepts). Read the exemption reasons: a rising count
     with weak reasons is the gate degrading into a comment ritual (WFT-40b) — compare against the
     previous week's run yourself, this script does not persist history.
   - **6. Coverage gaps** — what the report cannot see and why, stated explicitly rather than
     silently omitted. Read this before treating section 4 or 5 as complete pictures.
3. **Section 7 — tier critique (advisory, opt-in, WFT-96..109).** Not part of the six sections
   above; it never prints unless explicitly asked for, and it is two separate invocations, not one:
   - `--critique` scans the **current project's** persisted workflow scripts (same `--weeks`
     scoping as section 3) via `tier-scan.js --signals` and writes
     `.claude/sessions/tiercritic-packet.json` — an `entries` array covering every `agent()` call
     declaring `model: opus` or `fable`. Each entry carries an `excluded` boolean: `true` when the
     stage is itself a judgment stage (decided from `label`/`labelPrefix`/`phase` against a fixed
     keyword list, never from the prompt), `false` otherwise — the `false` entries are the
     **candidates**. No model call happens in this step.
   - **Observed tool-mix (WFT-93).** Each entry also carries `toolMix` (top-5 tool names by call
     count, e.g. `{"WebSearch": 42, "Bash": 4}`), `toolMixSource` (`"label"` when the join below
     succeeded, `"unknown"` when it did not — never a guessed/positional join), and
     `writeToolObserved` (`true`/`false`/`"unknown"`: whether Edit/Write/MultiEdit/NotebookEdit
     actually fired for that stage, the observed counterpart to the AST-only `writeToolReachable`).
     This is the third input WFT-93 specified and WFT-98 dropped: what a stage actually *did* at
     runtime, not just what its prompt/AST shape implies it should do — a prompt-only validator
     otherwise inherits and ratifies the same orchestrator's own misjudgement about the stage.
     The join key is the persisted script's own runid (`<name>-wf_<runid>.js`), which identifies
     one past workflow run — but not necessarily one manifest: a Workflow run can be **resumed
     under the same runId in a different session**, and each resumption session writes its own
     `<session>/workflows/wf_<runid>.json` for that same runId. The join therefore globs every
     manifest for `runid` under the **current project directory** (`~/.claude/projects/<slug>/**/
     workflows/wf_<runid>.json` — never leaving that directory, so this stays inside the WFT-101
     current-project-only boundary) and merges their `workflowProgress[]` label→agentId maps. An
     agentId named in more than one manifest is kept once (first manifest in sorted-path order),
     so its transcript — read from `<the session that manifest came from>/subagents/workflows/
     wf_<runid>/agent-<id>.jsonl`, not necessarily the script's own session — is never
     double-counted. The manifest's `workflowProgress[]` array is the *only* place a runtime
     `agentId` maps back to the `label` an authored `agent()` call declared — `agent-<id>.
     meta.json` siblings carry only `{agentType, model, spawnDepth, worktreePath}`, never a label
     (verified against thousands of real files). The join reads exactly three keys off each
     `workflowProgress` entry — `type`, `label`, `agentId` — and nothing else, from every manifest
     it opens: each manifest file *also* contains the full persisted script source and, per agent,
     truncated `promptPreview`/`resultPreview`/`lastToolSummary` text, none of which this script
     ever reads, stores, or prints. A call site with a statically-resolvable literal `label` joins
     on an exact match; a template-literal call (label option set to a template string, e.g.
     `audit:${f}`) joins on `labelPrefix`, aggregating tool counts over every runtime agent whose
     label starts with it (one `parallel()` fan-out call site expands into N runtime agents at N
     distinct labels). A call with neither joins to `toolMixSource: "unknown"` and `toolMix: {}`.
     Measured on this repo's own recent corpus: single-session join reached 56% (10/18); adding
     the cross-session manifest merge above raised it to 72% (13/18), with 23% of the joined
     entries (3/13) resolved *only* because of a manifest outside the script's own session — most
     visibly `gap-est`, previously unjoined and excluded from every finding by the WFT-101e
     evidence gate below. The remainder is a stated gap, not a zero, and no positional/ordinal
     join is attempted to close it. The report line `of those, joined only via a manifest from a
     session other than the script's own` states the cross-session count directly, so this effect
     is visible per-run rather than only in this doc.
   - **The classifier is the skill's only model call, shipped, and it runs only behind
     `--critique`.** Sections 1–6 and the packet step above are model-free by construction; this
     bullet is the sole place `/routing-audit` ever spawns a subagent. Concretely, the orchestrator:
     (1) reads `.claude/sessions/tiercritic-packet.json` and takes the `candidate` entries — those
     with `excluded: false`; (2) spawns `.claude/agents/tier-critic.md` via `Task` (`model: haiku`,
     `effort: low`, already pinned in that agent's frontmatter) with those candidate entries (or a
     path to the packet — the agent's prompt accepts either); (3) the agent returns a JSON array of
     `{id, tier, row?}` objects, one per candidate — `tier` one of `haiku|sonnet|opus|fable`, and an
     optional verbatim `row` string, the classifier's own claim of which `routing.tiers.json` row it
     matched, never something the render step infers (two rows can share a model — `sonnet` appears
     at both low and high effort — so deriving "the" row from the tier alone would assert a match
     nobody made); (4) the orchestrator writes that array, byte-for-byte, to a verdicts file under
     `.claude/sessions/` (e.g. `.claude/sessions/tiercritic-verdicts.json` — gitignored under the
     same D-049 entry as the packet and the log) and does not edit or filter it.
   - `--critique-render <verdicts.json>` prints section 7 against the last packet: only findings
     where the suggested tier is strictly cheaper than declared (never a raise, per WFT-97). Each
     finding's `row` is validated against the real `.assistant/routing.tiers.json` rows: present
     and matching → printed; absent → printed as `row: not stated`; present but unrecognised →
     the verdict is **not** rendered and counts toward `unclassified` instead (an unverifiable
     claim is treated the same as no verdict at all). The report also states the
     excluded/unclassified counts and the critic's own measured precision with its date. Each
     rendered finding is appended to `.claude/sessions/tiercritic.log`, keyed on `(file, line,
     callSha)` — not `label`, which only resolves statically for 52% of real calls — with an
     `accepted` field left blank for a human to fill in later. Any failure here (missing packet,
     malformed verdicts) prints `section 7: unavailable (<cause>)` and exits 0 — it never aborts
     the run.
4. If section 4 or the exemption count looks wrong for a specific stage, go read that
   `agent-*.jsonl` / workflow script directly — this report is a triage list, not a verdict.

## Notes

- No cost/money figures anywhere in this report, by design (WFT-40): no price list is in scope,
  and inventing one is forbidden. Token share of volume is not cost share — cache-read tokens
  dominate volume but are billed far cheaper per token (see section 6).
- Requires `python3` (stdlib only, no pip install) and `node` (for section 3 and for `--critique`
  only — the other sections degrade gracefully without it; the script itself still needs
  `python3`). `--critique-render` needs neither `node` nor a live transcript directory — it only
  reads the packet and verdicts files.
- If a number here differs materially from an older reference figure (e.g. an earlier spec's
  measured baseline), the report says so explicitly rather than silently reproducing it — a
  corrected classification rule can legitimately move a number by an order of magnitude, and
  quietly matching an old figure would just mean the rule wasn't actually fixed.
