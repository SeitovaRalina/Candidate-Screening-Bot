#!/usr/bin/env python3
# @spec:REQ-ROUTING-AUDIT
#
# Data engine for /routing-audit (WFT-40..44). Reads subagent transcripts under
# ~/.claude/projects/**/subagents/**/agent-*.jsonl and persisted Workflow scripts under
# ~/.claude/projects/**/workflows/scripts/*.js, and prints a plain-text report.
#
# Privacy boundary (WFT-40a): sections 1-6 read message.model, message.usage and tool_use
# `name` fields only, from agent-*.jsonl transcripts. They never read message text/content
# strings (prompts, tool inputs, tool outputs) and never print them. Default scope is the
# CURRENT project's transcript directory; machine-wide aggregation requires --all-projects.
#
# Section 7 (--critique, WFT-96..109) is the one deliberate exception: it reads the authored
# `agent()` prompt of the CURRENT project's own persisted workflow scripts, via
# `tier-scan.js --signals` over the AST — never via agent-*.jsonl (WFT-101b) — and refuses to
# run together with --all-projects (WFT-101). See SKILL.md for the full privacy contract.
#
# stdlib only — no pip install, matches the repo's zero-dependency convention for tooling
# that runs inside a hook/skill.

import argparse
import collections
import datetime
import glob
import json
import os
import re
import subprocess
import sys
import tempfile

HOME_PROJECTS = os.path.expanduser("~/.claude/projects")

DRIVER_TOOLS = {
    "screenshot", "snapshot_ui", "tap", "swipe", "boot_sim", "launch_app_sim",
    "build_sim", "install_app_sim", "browser_click", "browser_take_screenshot",
    "browser_navigate", "browser_snapshot",
}
WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
FRONTIER_TIERS = {"opus", "fable"}
CHEAP_TIERS = {"sonnet", "haiku"}

# --- section 7 (--critique / --critique-render, WFT-96..109) -----------------------

# WFT-99: judgment stages are excluded from flagging entirely, decided from label/labelPrefix/
# phase ONLY, never from the prompt body. English + Russian terms both appear in the real
# corpus. Order is the tie-break for `excludedBy` when more than one term would match.
JUDGMENT_KEYWORDS = [
    "audit", "review", "critic", "skeptic", "judge", "verify", "adversar", "plan",
    "проверк", "ревью", "критик", "скептик", "аудит", "план",
]

# opus and fable rank equal (WFT-97 never suggests a raise, and there is no tier above them
# to distinguish); haiku < sonnet < opus == fable is the only ordering section 7 needs.
CRITIQUE_TIER_ORDER = {"haiku": 0, "sonnet": 1, "opus": 2, "fable": 2}
VALID_CRITIQUE_TIERS = set(CRITIQUE_TIER_ORDER)

# WFT-106/107a: a constant carrying its own measurement date, not something re-typed each run.
# Twice-superseded, 2026-08-02: the n=59 cross-project gold-set figure below (79%) overstated
# live acceptance once measured hands-on; a first live measurement (5/6 = 83%, on findings with
# observed tool-mix, before join coverage was raised) then also went stale the same day when
# join coverage moved 10/18 -> 13/18 (72%, cross-session manifests). The wider joined set
# surfaced `gap-est` — the largest mis-tiered class — as a genuine true positive, but also cost
# precision: tool-mix alone cannot tell judgment work from mechanical work, and `est:`
# (skeptical estimators), `gap:` (adversarial search) and `accept` (an acceptance gate) all call
# StructuredOutput/Bash like a template-filler does, so the critic downgraded all three, wrongly,
# once their tool-mix became visible. The current 6/10 (60%) REPLACES the 5/6 figure — it is not
# an alternative reading, it is the same metric measured on the corrected, larger flag set. All
# three numbers stay in the line so none of this history is silently erased, and every one is
# stated as the small sample it is.
CRITIQUE_PRECISION_LINE = (
    "advisory — live flag acceptance measured 2026-08-02: 6/10 (60%) on the current packet "
    "(evidence gate on, cross-session joins enabled, join coverage 13/18 = 72%); supersedes an "
    "earlier same-day measurement of 5/6 (83%) taken before join coverage was raised, on a "
    "smaller flag set. Small samples throughout (n=10, n=6) — a cross-project gold set of 59 "
    "hand-labelled classes separately measured 79% and overstated live behaviour."
)


def slugify(path):
    # Matches Claude Code's project-directory naming: every character outside
    # [A-Za-z0-9-] becomes '-'. Verified against real ~/.claude/projects/* entries for
    # this repo's own cwd and worktree paths (both plain and dotted segments).
    return re.sub(r"[^A-Za-z0-9-]", "-", path)


def short_tool_name(name):
    if not name:
        return name
    if "__" in name:
        return name.rsplit("__", 1)[-1]
    return name


def tier_of(model):
    if not model or model == "<synthetic>":
        return None
    m = model.lower()
    if "opus" in m:
        return "opus"
    if "fable" in m:
        return "fable"
    if "sonnet" in m:
        return "sonnet"
    if "haiku" in m:
        return "haiku"
    return "other"


def iso_week(ts_iso):
    try:
        dt = datetime.datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
    except Exception:
        return None
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


def discover_project_dirs(all_projects, project_slug):
    if all_projects:
        if not os.path.isdir(HOME_PROJECTS):
            return []
        return sorted(
            d for d in glob.glob(os.path.join(HOME_PROJECTS, "*"))
            if os.path.isdir(d)
        )
    d = os.path.join(HOME_PROJECTS, project_slug)
    return [d] if os.path.isdir(d) else []


def scan_agent_file(fp):
    """Returns one record per agent transcript, or None if it never emitted a model."""
    first_model = None
    first_ts = None
    in_tok = cache_tok = out_tok = 0
    tool_names = []
    try:
        with open(fp, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                msg = d.get("message")
                if not isinstance(msg, dict) or msg.get("role") != "assistant":
                    continue
                m = msg.get("model")
                if first_model is None and m:
                    first_model = m
                    first_ts = d.get("timestamp")
                usage = msg.get("usage") or {}
                in_tok += usage.get("input_tokens", 0) or 0
                cache_tok += usage.get("cache_read_input_tokens", 0) or 0
                out_tok += usage.get("output_tokens", 0) or 0
                content = msg.get("content")
                if isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict) and c.get("type") == "tool_use":
                            tool_names.append(c.get("name"))
    except Exception:
        return None

    if not first_model:
        return None

    shorts = [short_tool_name(n) for n in tool_names]
    has_other_driver = any(s in DRIVER_TOOLS for s in shorts)
    driver_count = 0
    write_count = 0
    for s in shorts:
        if s in WRITE_TOOLS:
            write_count += 1
        if s in DRIVER_TOOLS:
            driver_count += 1
        elif s == "Bash" and has_other_driver:
            # Bash only counts toward drive/capture when it co-occurs with a genuine
            # driver tool in the SAME stage — it is also the verify/build/test channel
            # and the main tool of read-only research stages (see coverage-gaps: this
            # is a deliberate correction of a naive "Bash always counts" rule that
            # over-flags Bash-heavy research stages).
            driver_count += 1

    return {
        "model": first_model,
        "tier": tier_of(first_model),
        "ts": first_ts,
        "week": iso_week(first_ts) if first_ts else None,
        "input_tokens": in_tok,
        "cache_read_tokens": cache_tok,
        "output_tokens": out_tok,
        "tool_total": len(shorts),
        "driver_count": driver_count,
        "write_count": write_count,
        "tool_names": shorts,
    }


def weeks_cutoff(weeks_limit):
    if not weeks_limit:
        return None
    return datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(weeks=weeks_limit)


def collect_records(project_dirs, weeks_limit):
    records = []
    cutoff = weeks_cutoff(weeks_limit)
    for pdir in project_dirs:
        slug = os.path.basename(pdir.rstrip("/"))
        files = glob.glob(os.path.join(pdir, "**", "subagents", "**", "agent-*.jsonl"), recursive=True)
        for fp in files:
            rec = scan_agent_file(fp)
            if rec is None:
                continue
            if cutoff and rec["ts"]:
                try:
                    ts = datetime.datetime.fromisoformat(rec["ts"].replace("Z", "+00:00"))
                    if ts < cutoff:
                        continue
                except Exception:
                    pass
            rec["project"] = slug
            records.append(rec)
    return records


# --- section 1/2: token share + agent counts by tier -------------------------------

def section_token_share(records, top_projects):
    by_pw = collections.defaultdict(lambda: collections.defaultdict(lambda: {
        "input_tokens": 0, "cache_read_tokens": 0, "output_tokens": 0, "agents": 0,
    }))
    project_totals = collections.Counter()
    for r in records:
        if not r["week"]:
            continue
        tier = r["tier"] or "other"
        bucket = by_pw[(r["project"], r["week"])][tier]
        bucket["input_tokens"] += r["input_tokens"]
        bucket["cache_read_tokens"] += r["cache_read_tokens"]
        bucket["output_tokens"] += r["output_tokens"]
        bucket["agents"] += 1
        project_totals[r["project"]] += r["input_tokens"] + r["cache_read_tokens"] + r["output_tokens"]

    print("== 1. Tier share of token volume (input / cache-read / output), per project per ISO week ==")
    if not by_pw:
        print("(no dated subagent transcripts in scope)")
        print()
        return

    keys = sorted(by_pw.keys())
    shown_projects = set(p for p, _ in project_totals.most_common(top_projects)) if top_projects else None
    omitted = 0
    for (project, week) in keys:
        if shown_projects is not None and project not in shown_projects:
            omitted += 1
            continue
        tiers = by_pw[(project, week)]
        totals = {"input_tokens": 0, "cache_read_tokens": 0, "output_tokens": 0}
        for t in tiers.values():
            for k in totals:
                totals[k] += t[k]
        print(f"PROJECT {project}  WEEK {week}")
        for tier in ("opus", "fable", "sonnet", "haiku", "other"):
            if tier not in tiers:
                continue
            t = tiers[tier]
            def pct(field):
                tot = totals[field]
                return f"{100*t[field]/tot:.1f}%" if tot else "n/a"
            print(f"  {tier:<8} agents={t['agents']:<4} "
                  f"input={t['input_tokens']:>10,} ({pct('input_tokens')})  "
                  f"cache_read={t['cache_read_tokens']:>12,} ({pct('cache_read_tokens')})  "
                  f"output={t['output_tokens']:>10,} ({pct('output_tokens')})")
        print(f"  totals   input={totals['input_tokens']:,} cache_read={totals['cache_read_tokens']:,} "
              f"output={totals['output_tokens']:,}")
    if omitted:
        print(f"(+{omitted} project/week row(s) omitted — showing top {top_projects} project(s) by total tokens; "
              f"see the grand-total-by-week table below for the machine-wide figure)")

    # Rolled-up totals by week across every project in scope — the "summary table".
    by_week = collections.defaultdict(lambda: collections.defaultdict(lambda: {
        "input_tokens": 0, "cache_read_tokens": 0, "output_tokens": 0, "agents": 0,
    }))
    for (project, week), tiers in by_pw.items():
        for tier, t in tiers.items():
            b = by_week[week][tier]
            for k in ("input_tokens", "cache_read_tokens", "output_tokens", "agents"):
                b[k] += t[k]

    print()
    print("-- summary: all projects in scope, rolled up by ISO week --")
    for week in sorted(by_week.keys()):
        tiers = by_week[week]
        totals = {"input_tokens": 0, "cache_read_tokens": 0, "output_tokens": 0}
        for t in tiers.values():
            for k in totals:
                totals[k] += t[k]
        print(f"WEEK {week}  (input={totals['input_tokens']:,} cache_read={totals['cache_read_tokens']:,} "
              f"output={totals['output_tokens']:,})")
        for tier in ("opus", "fable", "sonnet", "haiku", "other"):
            if tier not in tiers:
                continue
            t = tiers[tier]
            def pct2(field):
                tot = totals[field]
                return f"{100*t[field]/tot:.1f}%" if tot else "n/a"
            print(f"  {tier:<8} agents={t['agents']:<4} input={pct2('input_tokens'):>6}  "
                  f"cache_read={pct2('cache_read_tokens'):>6}  output={pct2('output_tokens'):>6}")

    tot_all = sum(r["input_tokens"] + r["cache_read_tokens"] + r["output_tokens"] for r in records)
    tot_out = sum(r["output_tokens"] for r in records)
    if tot_all:
        print(f"\noutput_tokens are {100*tot_out/tot_all:.2f}% of all counted volume in this scope "
              f"(input+cache_read+output) — a share-of-output-only metric would be blind to the rest (WFT-40).")
    print()


def section_agent_counts(records):
    print("== 2. Agent counts by tier (frontier = opus|fable, cheap = sonnet|haiku) ==")
    by_project = collections.defaultdict(collections.Counter)
    for r in records:
        by_project[r["project"]][r["tier"] or "other"] += 1

    grand = collections.Counter()
    for project in sorted(by_project.keys()):
        c = by_project[project]
        frontier = sum(c[t] for t in FRONTIER_TIERS)
        cheap = sum(c[t] for t in CHEAP_TIERS)
        other = sum(v for k, v in c.items() if k not in FRONTIER_TIERS and k not in CHEAP_TIERS)
        total = frontier + cheap + other
        grand.update(c)
        print(f"  {project:<70} opus={c['opus']:<5} fable={c['fable']:<5} sonnet={c['sonnet']:<5} "
              f"haiku={c['haiku']:<5} other={other:<4} "
              f"| frontier={frontier}/{total} ({100*frontier/total:.1f}%)" if total else f"  {project}: no agents")
    total = sum(grand.values())
    frontier = sum(grand[t] for t in FRONTIER_TIERS)
    cheap = sum(grand[t] for t in CHEAP_TIERS)
    if total:
        print(f"  TOTAL {total} agents: opus={grand['opus']} ({100*grand['opus']/total:.1f}%)  "
              f"fable={grand['fable']} ({100*grand['fable']/total:.1f}%)  "
              f"sonnet={grand['sonnet']} ({100*grand['sonnet']/total:.1f}%)  "
              f"haiku={grand['haiku']} ({100*grand['haiku']/total:.1f}%)  "
              f"-- frontier {100*frontier/total:.1f}% / cheap {100*cheap/total:.1f}%")
    print()


# --- section 3: model/effort coverage across persisted workflow scripts ------------

def find_tier_scan(repo_root):
    p = os.path.join(repo_root, ".claude", "lib", "tier-scan.js")
    return p if os.path.isfile(p) else None


def run_tier_scan(detector, files):
    """Shells out to the shared detector (WFT-41: one detector, not two). Batches to
    stay well under any argv-length limit, and captures stdout via a temp FILE rather
    than a pipe: tier-scan.js calls process.exit() right after a single console.log of
    the whole verdict, and on a pipe (subprocess.PIPE) that truncates silently past
    ~64KB (observed: 65536-byte stdout, unparseable) because process.exit() does not
    wait for a pending async pipe flush on Node. A regular file has no such limit."""
    agg = {"agentCallsTotal": 0, "violations": [], "exemptions": [], "parseErrors": [], "filesOk": 0, "filesFailed": 0}
    if not files:
        return agg
    node = which("node")
    if not node:
        agg["parseErrors"].append("node not found on PATH — coverage section skipped")
        return agg
    CHUNK = 100
    for i in range(0, len(files), CHUNK):
        chunk = files[i:i + CHUNK]
        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(prefix="routing-audit-tierscan-", suffix=".json")
            os.close(fd)
            with open(tmp_path, "w", encoding="utf-8") as out_f:
                out = subprocess.run([node, detector] + chunk, stdout=out_f,
                                      stderr=subprocess.PIPE, text=True, timeout=60)
            with open(tmp_path, "r", encoding="utf-8") as f:
                raw = f.read()
        except Exception as e:
            agg["parseErrors"].append(f"detector invocation failed: {e}")
            continue
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
        try:
            result = json.loads(raw)
        except Exception:
            agg["parseErrors"].append(f"detector produced non-JSON output (exit {out.returncode})")
            continue
        agg["agentCallsTotal"] += result.get("agentCalls", 0)
        agg["violations"].extend(result.get("violations", []))
        agg["exemptions"].extend(result.get("exemptions", []))
        if result.get("parseError"):
            agg["parseErrors"].append(result["parseError"])
            agg["filesFailed"] += len(chunk)
        else:
            agg["filesOk"] += len(chunk)
    return agg


def which(cmd):
    for d in os.environ.get("PATH", "").split(os.pathsep):
        p = os.path.join(d, cmd)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


def discover_workflow_scripts(project_dirs):
    all_files = []
    for pdir in project_dirs:
        all_files.extend(glob.glob(os.path.join(pdir, "**", "workflows", "scripts", "*.js"), recursive=True))
    return sorted(set(all_files))


def filter_scripts_by_weeks(files, weeks_limit):
    """mtime-based filter, shared by section 3 and the --critique packet (WFT-96 honours
    --weeks the same way section 3 does)."""
    cutoff = weeks_cutoff(weeks_limit)
    if not cutoff:
        return list(files)
    kept = []
    for fp in files:
        try:
            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(fp), tz=datetime.timezone.utc)
        except OSError:
            continue
        if mtime >= cutoff:
            kept.append(fp)
    return kept


def section_workflow_coverage(project_dirs, detector, weeks_limit):
    print("== 3. model:/effort: coverage across persisted workflow scripts (<session>/workflows/scripts/*.js) ==")
    all_files = discover_workflow_scripts(project_dirs)

    cutoff = weeks_cutoff(weeks_limit)
    if cutoff:
        files = filter_scripts_by_weeks(all_files, weeks_limit)
        print(f"  {len(all_files)} script file(s) on disk, {len(files)} in the last {weeks_limit} week(s)")
    else:
        files = all_files
        print(f"  {len(files)} script file(s) in scope")
    if not files:
        print()
        return None
    if not detector:
        print("  SKIP: .claude/lib/tier-scan.js not found (needed to reuse the L2 gate's detector, WFT-41)")
        print()
        return None

    agg = run_tier_scan(detector, files)
    calls = agg["agentCallsTotal"]
    print(f"  agent() calls: {calls}")
    if agg["parseErrors"]:
        print(f"  parse failures: {len(agg['parseErrors'])} (batch(es) reporting: "
              f"{'; '.join(agg['parseErrors'][:3])}{' ...' if len(agg['parseErrors']) > 3 else ''})")
    else:
        print("  parse failures: 0")

    # De-dup violations by (file, line) — a single call can push more than one kind
    # ('no-model' and 'no-effort' both, for the same call). "Undecidable"/"no-opts" imply
    # neither field is valid.
    def kind_calls(kind_set):
        return {(v["file"], v["line"]) for v in agg["violations"] if v["kind"] in kind_set}

    no_model_calls = kind_calls({"no-model", "undecidable", "no-opts"})
    no_effort_calls = kind_calls({"no-effort", "undecidable", "no-opts"})
    valid_model = calls - len(no_model_calls) if calls else 0
    valid_effort = calls - len(no_effort_calls) if calls else 0
    print(f"  calls with a valid literal model:  {valid_model}/{calls}"
          f" ({100*valid_model/calls:.0f}%)" if calls else "  calls with a valid literal model: n/a")
    print(f"  calls with a valid literal effort: {valid_effort}/{calls}"
          f" ({100*valid_effort/calls:.0f}%)" if calls else "  calls with a valid literal effort: n/a")
    print(f"  exempted calls (// tier-exempt: <reason>): {len(agg['exemptions'])}")
    print("  NOTE: the detector's public verdict does not separately expose 'model key present but "
          "invalid value' vs 'model key absent' — both collapse into the same 'no-model' violation "
          "kind, so only the valid-vs-not-valid split above is reproducible without a second parser "
          "(WFT-41 forbids writing one). See coverage-gaps.")
    print()
    return agg


# --- section 4: deterministic mis-tier flags ----------------------------------------

def section_mis_tier(records):
    print("== 4. Deterministic mis-tier flags (drive/capture-heavy frontier stages, WFT-42/43) ==")
    flagged = []
    for r in records:
        if r["tier"] not in FRONTIER_TIERS:
            continue
        if r["tool_total"] == 0:
            continue
        ratio = r["driver_count"] / r["tool_total"]
        if ratio > 0.5 and r["write_count"] == 0:
            flagged.append(r)
    out_tok = sum(r["output_tokens"] for r in flagged)
    print(f"  flagged stages: {len(flagged)}   output tokens involved: {out_tok:,}")
    if flagged:
        by_project = collections.Counter(r["project"] for r in flagged)
        for project, n in by_project.most_common(10):
            print(f"    {project}: {n} flagged stage(s)")
    print("  Rule: >50% of a stage's tool calls are drive/capture "
          "(screenshot/snapshot_ui/tap/swipe/boot_sim/launch_app_sim/build_sim/install_app_sim/"
          "browser_click/browser_take_screenshot/browser_navigate/browser_snapshot), zero file writes "
          "(Edit/Write/MultiEdit/NotebookEdit), and a frontier model. Bash counts toward drive/capture "
          "ONLY when it co-occurs with a genuine driver tool in the same stage — it is also the "
          "verify/build/test channel and the main tool of read-only research stages, so counting it "
          "unconditionally over-flags those.")
    print()
    return flagged


# --- section 5: gate health ----------------------------------------------------------

def parse_tierwarn_log(path):
    warnings = []
    if not os.path.isfile(path):
        return warnings
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if line:
                warnings.append(line)
    return warnings


# D-051: tierpreflight.log lines share tierwarn.log's own format — a leading timestamp token
# (no "=" in it, so this split naturally drops it) followed by space-separated key=value pairs.
def parse_kv_line(line):
    fields = {}
    for tok in line.split(" "):
        if "=" in tok:
            k, _, v = tok.partition("=")
            fields[k] = v
    return fields


def parse_tiercritic_shas(path):
    """Every callSha that tier-critic has already rendered a verdict for, regardless of what
    the verdict was — D-051's escalation gate only re-denies on a callSha absent from this set."""
    shas = set()
    if not os.path.isfile(path):
        return shas
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            sha = d.get("callSha")
            if sha:
                shas.add(sha)
    return shas


def section_gate_health(repo_root, workflow_agg):
    print("== 5. Gate-health (WFT-40b) ==")
    print("  Scope note: fan-out log and gate-activation state are REPO-LOCAL "
          "(.claude/sessions/ and the current project's own SessionStart injections). "
          "They are reported for the current repo regardless of --all-projects.")

    exemptions = (workflow_agg or {}).get("exemptions", [])
    print(f"  // tier-exempt: uses: {len(exemptions)}")
    for e in exemptions[:30]:
        print(f"    {e['file']}:{e['line']}  reason: {e['reason']!r}")
    if len(exemptions) > 30:
        print(f"    ...and {len(exemptions) - 30} more")
    print("  NOTE: this is a single-run count. Detecting a *rising* trend (WFT-40b) requires "
          "comparing against a prior run's count — not persisted by this script; see coverage-gaps.")

    tierwarn_path = os.path.join(repo_root, ".claude", "sessions", "tierwarn.log")
    warnings = parse_tierwarn_log(tierwarn_path)
    print(f"  fan-out warnings ({tierwarn_path}): {len(warnings)}")
    for w in warnings[-10:]:
        print(f"    {w}")

    # D-051: tier-preflight is a non-blocking pre-launch signal (shape-mismatch heuristic +
    # opus/fable budget ceiling, see workflow-tier-gate.sh) — every entry in this log is a
    # Workflow that launched anyway, either because a human already had tier-critic weigh in
    # (callSha present in tiercritic.log) or because the launch is still outstanding. Safety
    # lives in this tally, not in the classifier — this is the tally.
    tierpreflight_path = os.path.join(repo_root, ".claude", "sessions", "tierpreflight.log")
    preflight_entries = [parse_kv_line(w) for w in parse_tierwarn_log(tierpreflight_path)]
    tiercritic_path = os.path.join(repo_root, ".claude", "sessions", "tiercritic.log")
    tiercritic_shas = parse_tiercritic_shas(tiercritic_path)
    print(f"  tier-preflight launches-anyway tally ({tierpreflight_path}): {len(preflight_entries)} logged flag(s)")
    unique_calls = {
        (e.get("file"), e.get("line"), e.get("callSha"))
        for e in preflight_entries if e.get("callSha")
    }
    reviewed = {c for c in unique_calls if c[2] in tiercritic_shas}
    outstanding = len(unique_calls) - len(reviewed)
    print(f"    unique flagged call sites: {len(unique_calls)}   "
          f"already reviewed (callSha in tiercritic.log): {len(reviewed)}   outstanding: {outstanding}")
    reasons = collections.Counter(e.get("reason") for e in preflight_entries if e.get("reason"))
    if reasons:
        print("    by flag reason: " + "  ".join(f"{k}={v}" for k, v in sorted(reasons.items())))

    print("  HARNESS_TIER_GATE=off: NOT reported here. Two things were tried and rejected during the "
          "build of this audit: (1) workflow-tier-gate.sh exits before writing any log line when the "
          "off-switch is set (line 18), so there is no hook-authored record of the event at all; "
          "(2) grepping session transcripts for inject-state.sh's 'workflow-tier-gate: ACTIVE|INERT: "
          "...' status line was tried and measurably unreliable — the identical string also shows up "
          "in tool_result output from anyone manually testing the hook, and in ordinary prose "
          "discussing this feature (verified against this repo's own build session), so a text match "
          "cannot tell a genuine SessionStart injection apart from those. Reporting a grep-derived "
          "count would have been more misleading than reporting nothing. See coverage-gaps.")
    print()


# --- section 6: coverage gaps ---------------------------------------------------------

def section_coverage_gaps():
    print("== 6. Coverage gaps (WFT-44) — what this audit cannot see ==")
    print("""  - No cost/money figures are computed anywhere in this report, by design (WFT-40): no
    price list is in scope for this audit and inventing one is forbidden. Token counts are
    NOT a cost proxy on their own — see the next point.
  - cache_read_input_tokens is the largest field by volume but is billed far cheaper per
    token than input/output tokens. A large cache-read share therefore does NOT mean a large
    cost share; token-volume share and cost share are different quantities and this report
    only measures the former.
  - The read/judge class is invisible to any keyword-based rule. Per the REQ-WORKFLOW-TIER
    evidence base (2026-07-25): 2,925 agents / 9,536,276 output tokens match "judgment"
    keywords purely because those keywords appear in harness prompt boilerplate (69% of
    matches) — a keyword verdict on that class is the null action wearing a decision's
    clothes. This audit does not attempt keyword-based judgment classification for exactly
    that reason (WFT-43: no LLM verdicts either, so this class stays unclassified rather than
    mis-classified).
  - Section 4's driver-tool list is the literal set given in WFT-42. MCP families that expose
    a single dispatch tool with an action *parameter* rather than a per-action tool name (for
    example mcp__mobile__input/ui/screen, where tap/swipe/screenshot are argument values, not
    tool_use `name` values) are NOT decomposed by this script and are likely undercounted for
    that family. Extending the list to parse tool_input action fields would need to read
    tool_input, which risks catching prompt-shaped content — out of scope under the privacy
    boundary (WFT-40a).
  - HARNESS_TIER_GATE=off usage is not observable at all by this script (see section 5):
    workflow-tier-gate.sh writes no log line when the switch is set, and grepping session
    transcripts for the SessionStart status string was tried and rejected as unreliable
    (the same string appears in unrelated tool output and prose). This is a genuine blind
    spot, not a verified zero.
  - The "rising exemption count" regression check (WFT-40b) needs a time series of prior
    audit runs; this script reports one point-in-time count, not a trend. Wire this into a
    weekly-persisted history if the trend check becomes load-bearing.
  - --all-projects fan-out/gate-state figures (section 5) are not attempted: tierwarn.log and
    the gate SessionStart lines live under each repo's own .claude/ tree, and a transcript
    directory's slugified name does not invert cleanly back to a filesystem path across all
    machine projects. Section 5 always reports the current repo only.
  - Section 4's flag count is sensitive to the Bash co-occurrence rule by roughly an order of
    magnitude: counting Bash unconditionally as drive/capture (the literal WFT-42 wording,
    before this build's correction) measures ~30-100x more flagged stages on this machine's
    corpus than the corrected co-occurrence rule this script implements. If a reported figure
    here reads far lower than an earlier "~200 agents" reference number, that is this fix
    taking effect, not a measurement error — the earlier number very likely counted ordinary
    Bash-only research/verify stages as false positives.
  - Section 3 without --weeks globs every persisted workflow script this machine has ever
    written, pre-gate and post-gate alike, and reports one blended coverage percentage. That
    number understates current compliance and should not be read as "is the gate working" —
    pass --weeks N to scope section 3 to scripts written in the last N weeks and get a
    figure that reflects gated behaviour rather than pre-gate history.""")
    print()


# --- section 7: tier critique (advisory, --critique / --critique-render, WFT-96..109) ----

def run_tier_scan_signals(detector, files):
    """Same batching/tempfile approach as run_tier_scan (WFT-41: one detector). --signals
    output carries authored prompt text so it lands only in the packet file, never in this
    function's return value being printed directly."""
    records = []
    errors = []
    if not files:
        return records, errors
    node = which("node")
    if not node:
        errors.append("node not found on PATH")
        return records, errors
    CHUNK = 100
    for i in range(0, len(files), CHUNK):
        chunk = files[i:i + CHUNK]
        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(prefix="routing-audit-tiersignals-", suffix=".json")
            os.close(fd)
            with open(tmp_path, "w", encoding="utf-8") as out_f:
                subprocess.run([node, detector, "--signals"] + chunk, stdout=out_f,
                                stderr=subprocess.PIPE, text=True, timeout=60)
            with open(tmp_path, "r", encoding="utf-8") as f:
                raw = f.read()
        except Exception as e:
            errors.append(f"detector invocation failed: {e}")
            continue
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
        try:
            batch = json.loads(raw)
        except Exception:
            errors.append("detector produced non-JSON --signals output")
            continue
        records.extend(batch)
    return records, errors


def classify_judgment(label, label_prefix, phase):
    """WFT-99: decided from label/labelPrefix/phase only, never from the prompt body."""
    for value in (label, label_prefix, phase):
        if not value:
            continue
        low = value.lower()
        for kw in JUDGMENT_KEYWORDS:
            if kw in low:
                return kw
    return None


def project_dir_of(file_path, project_dirs):
    for pdir in project_dirs:
        if file_path.startswith(pdir.rstrip("/") + os.sep):
            return pdir
    return None


# --- WFT-93 restoration: observed tool-mix, joined onto the critique packet --------
#
# WFT-93 required a third input the classifier never got: what the stage actually
# DID at runtime, as opposed to what its prompt/AST shape says it should do. The join
# key is the persisted script's own runid ("<name>-wf_<runid>.js"), which identifies
# exactly one past workflow run.
#
# A run's manifest is NOT guaranteed to live only under the session that holds the
# persisted script: a Workflow can be resumed under the same runId in a different
# session, and each resumption session writes its own "<session>/workflows/wf_<runid>.
# json" for that same runId. Joining only against the script's own session therefore
# silently dropped every stage whose manifest entry landed in a different session —
# measured on this machine at 10/18 (56%) join coverage before this fix, with entire
# label families (e.g. every "gap:*" / "est:*" stage) missing purely because their
# manifest lived elsewhere. load_workflow_manifest_agents() now globs every manifest
# for `runid` under the CURRENT PROJECT directory only (WFT-101: --critique stays
# current-project-only; this join must never widen that to ~/.claude/projects/*) and
# merges their label->agentId maps, keeping the session root each agentId was found in
# so its transcript is read from the session that actually ran it, not from the
# script's own session.
#
# The manifest is NOT an agent-*.jsonl transcript, so it sits outside the "meta.json
# siblings" file set this feature was scoped around. It is read here because it is the
# ONLY place a runtime agentId maps back to the `label` an authored agent() call
# declared; agent-<id>.meta.json carries only {agentType, model, spawnDepth,
# worktreePath} (verified against 8771 real files on this machine — never a label).
# The manifest also carries "script" (the full persisted source) and, per
# workflow_agent entry, "promptPreview"/"resultPreview"/"lastToolSummary" — truncated
# prompt and output text. Those four keys are never read here: for every manifest it
# opens, load_workflow_manifest_agents() takes only "type", "label", "agentId" off
# each workflowProgress entry and discards the rest of the parsed object immediately.
# No prompt/output text from this file is ever placed in toolMix, toolMixSource,
# writeToolObserved, or anywhere else this script writes or prints.
WF_RUNID_RE = re.compile(r"(wf_[0-9a-f]+-[0-9a-f]+)\.js$")


def script_runid(script_path):
    m = WF_RUNID_RE.search(os.path.basename(script_path))
    return m.group(1) if m else None


def session_root_of_script(script_path):
    # <session>/workflows/scripts/<name>-wf_<runid>.js -> <session>
    scripts_dir = os.path.dirname(script_path)
    workflows_dir = os.path.dirname(scripts_dir)
    return os.path.dirname(workflows_dir)


def find_manifest_paths_for_runid(project_dir, runid):
    # Recursive "**" mirrors discover_workflow_scripts' own pattern (session roots are not
    # guaranteed to sit exactly one level below project_dir, e.g. worktree paths), but the
    # walk is rooted at project_dir and never leaves it — that is what keeps this WFT-101
    # current-project-only.
    pattern = os.path.join(project_dir, "**", "workflows", f"{runid}.json")
    return sorted(set(glob.glob(pattern, recursive=True)))


def session_root_of_manifest(manifest_path):
    # <session>/workflows/<runid>.json -> <session>
    workflows_dir = os.path.dirname(manifest_path)
    return os.path.dirname(workflows_dir)


def load_workflow_manifest_agents(project_dir, runid, manifest_cache):
    """Merges the label->agentId map across every manifest this project holds for `runid`.
    An agentId seen in more than one manifest is kept once — from the first manifest, in
    sorted-path order, that names it — so its transcript is read once, never double-counted."""
    key = (project_dir, runid)
    if key in manifest_cache:
        return manifest_cache[key]
    agents_by_id = {}
    for manifest_path in find_manifest_paths_for_runid(project_dir, runid):
        session_root = session_root_of_manifest(manifest_path)
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        for item in data.get("workflowProgress", []):
            if not isinstance(item, dict) or item.get("type") != "workflow_agent":
                continue
            agent_id = item.get("agentId")
            if not agent_id or agent_id in agents_by_id:
                continue
            agents_by_id[agent_id] = {"label": item.get("label"), "session_root": session_root}
    result = agents_by_id if agents_by_id else None
    manifest_cache[key] = result
    return result


def tool_mix_for_agent_id(session_root, runid, agent_id, mix_cache):
    key = (session_root, runid, agent_id)
    if key in mix_cache:
        return mix_cache[key]
    fp = os.path.join(session_root, "subagents", "workflows", runid, f"agent-{agent_id}.jsonl")
    rec = scan_agent_file(fp)
    result = None if rec is None else (collections.Counter(rec["tool_names"]),
                                        any(n in WRITE_TOOLS for n in rec["tool_names"]))
    mix_cache[key] = result
    return result


def join_tool_mix(r, project_dir, manifest_cache, mix_cache):
    """label-only join (WFT-93, extended for cross-session manifests per the comment
    block above load_workflow_manifest_agents): exact match on a
    statically-resolvable literal `label`, or prefix match on a template-literal
    `labelPrefix` aggregated over every runtime agent whose label starts with it (a
    `label: audit:${f}` call site fans out into N runtime agents at N distinct labels
    sharing that prefix). Matching agents are pulled from the merged, project-wide
    manifest map — not just the script's own session — but each agent's transcript is
    read from the session root it was actually recorded under. No positional/ordinal
    join is attempted — an ordering assumption across parallel() fan-out is not
    something this script can verify, so it is not guessed. Returns (toolMix dict
    capped top-5, toolMixSource, writeToolObserved, crossSessionOnly): crossSessionOnly
    is True only when the join succeeded and every matching runtime agent was found in
    a session other than the one the persisted script itself lives in — i.e. the join
    would have failed entirely (toolMixSource stays "unknown") without consulting
    another session's manifest."""
    runid = script_runid(r["file"])
    if not runid or not project_dir:
        return {}, "unknown", "unknown", False
    own_session_root = session_root_of_script(r["file"])
    agents_by_id = load_workflow_manifest_agents(project_dir, runid, manifest_cache)
    if not agents_by_id:
        return {}, "unknown", "unknown", False

    label = r.get("label")
    label_prefix = r.get("labelPrefix")
    if label:
        matched = [(aid, a) for aid, a in agents_by_id.items() if a["label"] == label]
    elif label_prefix:
        matched = [(aid, a) for aid, a in agents_by_id.items()
                   if a["label"] and a["label"].startswith(label_prefix)]
    else:
        matched = []
    if not matched:
        return {}, "unknown", "unknown", False

    total = collections.Counter()
    any_readable = False
    any_write = False
    for aid, a in matched:
        res = tool_mix_for_agent_id(a["session_root"], runid, aid, mix_cache)
        if res is None:
            continue
        counter, wrote = res
        any_readable = True
        total.update(counter)
        any_write = any_write or wrote

    if not any_readable:
        return {}, "unknown", "unknown", False
    cross_session_only = all(a["session_root"] != own_session_root for _, a in matched)
    return dict(total.most_common(5)), "label", any_write, cross_session_only


def build_critique_packet(project_dirs, detector, weeks_limit, repo_root, project_slug):
    print("== critique packet (WFT-96, --critique) ==")
    all_files = discover_workflow_scripts(project_dirs)
    files = filter_scripts_by_weeks(all_files, weeks_limit)
    print(f"  scripts in scope: {len(files)}")
    if not files:
        print("  no persisted workflow scripts in scope; nothing to critique")
        print()
        return
    if not detector:
        print("  SKIP: .claude/lib/tier-scan.js not found (needed for --signals, WFT-41)")
        print()
        return

    raw_records, errors = run_tier_scan_signals(detector, files)
    if errors:
        print(f"  detector errors: {len(errors)} ({'; '.join(errors[:3])}{' ...' if len(errors) > 3 else ''})")

    entries = []
    excluded_entries = []
    candidate_n = 0
    manifest_cache = {}
    mix_cache = {}
    joined_n = 0
    cross_session_joined_n = 0
    for r in raw_records:
        model = r.get("model")
        # WFT-97: a stage already on sonnet/haiku is never a downgrade candidate, and there is
        # nothing to critique on a call with no declared model at all (that is an L2 concern,
        # already surfaced by section 3) — so only opus/fable calls enter the packet.
        if model not in ("opus", "fable"):
            continue
        matched_kw = classify_judgment(r.get("label"), r.get("labelPrefix"), r.get("phase"))
        excluded = matched_kw is not None
        pdir = project_dir_of(r["file"], project_dirs)
        relpath = os.path.relpath(r["file"], pdir) if pdir else r["file"]
        tool_mix, tool_mix_source, write_observed, cross_session_only = join_tool_mix(
            r, pdir, manifest_cache, mix_cache
        )
        if tool_mix_source != "unknown":
            joined_n += 1
            if cross_session_only:
                cross_session_joined_n += 1
        entry = {
            "id": f"{relpath}:{r['line']}:{r['callSha']}",
            "file": relpath,
            "line": r["line"],
            "callSha": r["callSha"],
            "label": r.get("label"),
            "labelPrefix": r.get("labelPrefix"),
            "labelStatic": r.get("labelStatic"),
            "phase": r.get("phase"),
            "model": model,
            "effort": r.get("effort"),
            "schema": r.get("schema"),
            "writeToolReachable": r.get("writeToolReachable"),
            "feedsJudgment": r.get("feedsJudgment"),
            "prompt": r.get("prompt"),
            "excluded": excluded,
            "excludedBy": matched_kw,
            "toolMix": tool_mix,
            "toolMixSource": tool_mix_source,
            "writeToolObserved": write_observed,
        }
        entries.append(entry)
        if excluded:
            excluded_entries.append(entry)
        else:
            candidate_n += 1

    sessions_dir = os.path.join(repo_root, ".claude", "sessions")
    os.makedirs(sessions_dir, exist_ok=True)
    packet_path = os.path.join(sessions_dir, "tiercritic-packet.json")
    packet = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "project_slug": project_slug,
        "weeks": weeks_limit,
        "entries": entries,
    }
    with open(packet_path, "w", encoding="utf-8") as f:
        json.dump(packet, f, indent=2)
        f.write("\n")

    print(f"  agent() calls found: {len(raw_records)}")
    print(f"  candidates (opus/fable, non-judgment): {candidate_n}")
    print(f"  excluded (judgment stages): {len(excluded_entries)}")
    for e in excluded_entries:
        print(f"    excluded: {e['id']}  matched term: {e['excludedBy']!r}")
    joined_pct = f"{100*joined_n/len(entries):.0f}%" if entries else "n/a"
    print(f"  toolMix joined (label/labelPrefix match, WFT-93): {joined_n}/{len(entries)} ({joined_pct}); "
          f"remainder is toolMixSource: unknown, toolMix: {{}} — never guessed")
    cross_pct = f"{100*cross_session_joined_n/joined_n:.0f}%" if joined_n else "n/a"
    print(f"  of those, joined only via a manifest from a session other than the script's own "
          f"(cross-session resume): {cross_session_joined_n}/{joined_n} ({cross_pct})")
    print(f"  packet: {packet_path}")
    print()


def load_routing_rows(repo_root):
    p = os.path.join(repo_root, ".assistant", "routing.tiers.json")
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("rows", [])


# Sentinel distinct from `None`: `lookup_row(rows, None)` (verdict carried no `row` at all) must
# be told apart from `lookup_row(rows, "bogus")` returning "no match found" — the former renders
# as "row: not stated", the latter is not a finding at all (counts toward unclassified instead).
_ROW_NOT_STATED = object()


def lookup_row(rows, row_text):
    """The row is asserted by the VERDICT, never reverse-derived from the suggested tier: two
    routing.tiers.json rows can share a model (sonnet appears at both low and high effort), so
    picking "the" row for a tier would assert a match the classifier never made."""
    if row_text is None:
        return _ROW_NOT_STATED
    for row in rows:
        if row.get("stage") == row_text:
            return f"{row.get('stage')} ({row.get('model')}/{row.get('effort')})"
    return None  # present but does not match any real row — caller treats as unclassified


def build_finding(entry, suggested_tier, row_display):
    # WFT-101a closed vocabulary: signal names/values, label/labelPrefix, phase, and the
    # verdict-asserted routing.tiers.json row text — never the prompt. Declared/suggested tier
    # are already printed on their own line by the caller; the reason does not repeat them.
    reason = (
        f"label={entry.get('label')!r} labelPrefix={entry.get('labelPrefix')!r} "
        f"phase={entry.get('phase')!r} schema={entry.get('schema')} "
        f"writeToolReachable={entry.get('writeToolReachable')} "
        f"feedsJudgment={entry.get('feedsJudgment')} -- {row_display}"
    )
    return {
        "id": entry["id"], "file": entry["file"], "line": entry["line"], "callSha": entry["callSha"],
        "declared": entry["model"], "suggested": suggested_tier,
        "label": entry.get("label"), "phase": entry.get("phase"), "reason": reason,
    }


def render_critique(verdicts_path, repo_root, no_evidence_gate=False):
    """WFT-109: a separate invocation, never a seventh call inside main()'s unguarded
    section 1-6 sequence. Everything is computed before anything is printed or written, so a
    failure at any point yields exactly one line and exit 0 — never partial output.

    WFT-101e evidence gate: three live hand-reviewed runs measured 83% acceptance on findings
    joined to observed toolMix (toolMixSource == "label") against 0% on findings with no such
    join (toolMixSource == "unknown") — n=6 and n=3, too small to generalize beyond "do not ship
    a finding with no independent evidence", which is the rule this gate enforces regardless of
    sample size. A downgrade candidate without an observed tool-mix is withheld, not rendered,
    and never appended to tiercritic.log. --no-evidence-gate exists to measure the gate against
    itself (re-running the ungated packet through /routing-audit's own review loop)."""
    try:
        packet_path = os.path.join(repo_root, ".claude", "sessions", "tiercritic-packet.json")
        with open(packet_path, "r", encoding="utf-8") as f:
            packet = json.load(f)
        with open(verdicts_path, "r", encoding="utf-8") as f:
            verdicts = json.load(f)
        if not isinstance(verdicts, list):
            raise ValueError("verdicts file must be a JSON array of {id, tier, row?} objects")

        verdict_by_id = {}
        for v in verdicts:
            if not isinstance(v, dict):
                continue
            vid = v.get("id")
            if vid is not None:
                verdict_by_id[vid] = v

        rows = load_routing_rows(repo_root)
        entries = packet.get("entries", [])
        candidates = [e for e in entries if not e.get("excluded")]
        excluded_n = sum(1 for e in entries if e.get("excluded"))

        findings = []
        unclassified = 0
        withheld = []
        for e in candidates:
            v = verdict_by_id.get(e["id"])
            vtier = v.get("tier") if isinstance(v, dict) else None
            if vtier not in VALID_CRITIQUE_TIERS:
                # WFT-107: no verdict, or an out-of-enum one — counted, never silently dropped.
                unclassified += 1
                continue
            declared = e["model"]
            if CRITIQUE_TIER_ORDER[vtier] >= CRITIQUE_TIER_ORDER[declared]:
                continue  # not a downgrade — correctly classified, not a finding, not unclassified

            # WFT-101e evidence gate: a downgrade with no observed tool-mix (toolMixSource != "label"
            # — no join at all, or only a prefix match that never resolved a live agent) measured 0/3
            # live acceptance against 5/6 when the join held. Withheld, never rendered, never logged —
            # a stated gap (below), same discipline as `unclassified`, not a silent drop.
            if not no_evidence_gate and e.get("toolMixSource") != "label":
                withheld.append(e)
                continue

            row_display = lookup_row(rows, v.get("row"))
            if row_display is None:
                # The verdict asserted a row that does not exist in routing.tiers.json — an
                # unverifiable claim, so the whole verdict is unclassified rather than rendered
                # on a fabricated basis.
                unclassified += 1
                continue
            row_display = "row: not stated" if row_display is _ROW_NOT_STATED else f"row: {row_display!r}"
            findings.append(build_finding(e, vtier, row_display))

        report_lines = [
            "== 7. Tier critique (advisory) ==",
            "  critic tier: declared haiku/low (WFT-100)",
            f"  candidates: {len(candidates)}   excluded: {excluded_n}   "
            f"unclassified: {unclassified}   findings: {len(findings)}",
            f"  withheld (no observed tool-mix, WFT-101e): {len(withheld)}",
        ]
        if no_evidence_gate:
            report_lines.append(
                "  --no-evidence-gate: WFT-101e evidence gate bypassed — every downgrade candidate "
                "is rendered regardless of toolMixSource"
            )
        report_lines.append(f"  {CRITIQUE_PRECISION_LINE}")
        for f_ in findings:
            report_lines.append(f"  {f_['id']}")
            report_lines.append(f"    declared {f_['declared']} -> suggested {f_['suggested']}")
            report_lines.append(f"    {f_['reason']}")

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        log_lines = [json.dumps({
            "timestamp": now, "file": f_["file"], "line": f_["line"], "callSha": f_["callSha"],
            "declared": f_["declared"], "suggested": f_["suggested"], "label": f_["label"],
            "phase": f_["phase"], "reason": f_["reason"], "accepted": "",
        }) for f_ in findings]

        if log_lines:
            sessions_dir = os.path.join(repo_root, ".claude", "sessions")
            os.makedirs(sessions_dir, exist_ok=True)
            log_path = os.path.join(sessions_dir, "tiercritic.log")
            with open(log_path, "a", encoding="utf-8") as logf:
                for line in log_lines:
                    logf.write(line + "\n")
    except Exception as e:
        print(f"section 7: unavailable ({e})")
        return 0

    print("\n".join(report_lines))
    return 0


# --- main ------------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Report on routing tier compliance from local Claude Code transcripts.")
    ap.add_argument("--all-projects", action="store_true",
                     help="Aggregate machine-wide across ~/.claude/projects/** instead of the current project only. "
                          "WFT-40a: off by default for privacy.")
    ap.add_argument("--weeks", type=int, default=None, help="Limit to the last N weeks.")
    ap.add_argument("--top-projects", type=int, default=20,
                     help="Cap the per-project weekly table to the top N projects by token volume (--all-projects only).")
    ap.add_argument("--repo-root", default=None, help="Override the harness repo root (default: auto-detected).")
    ap.add_argument("--cwd", default=None, help="Override the cwd used to compute the current project's slug.")
    ap.add_argument("--critique", action="store_true",
                     help="Emit a section-7 signal packet (WFT-96..101) for the current project's persisted "
                          "workflow scripts. No model call is made here. Refuses to combine with --all-projects.")
    ap.add_argument("--critique-render", metavar="VERDICTS_JSON", default=None,
                     help="Render section 7 from a verdicts file (produced against the last --critique packet). "
                          "A separate invocation (WFT-109) — prints only section 7 and nothing else.")
    ap.add_argument("--no-evidence-gate", action="store_true",
                     help="Bypass the WFT-101e evidence gate: render every downgrade candidate regardless of "
                          "toolMixSource. Only valid with --critique-render; exists to measure the gate against "
                          "itself.")
    args = ap.parse_args()

    repo_root = args.repo_root or find_repo_root()
    cwd = args.cwd or os.getcwd()
    project_slug = slugify(os.path.abspath(cwd))

    if args.critique_render:
        return render_critique(args.critique_render, repo_root, no_evidence_gate=args.no_evidence_gate)

    print("routing-audit")
    print(f"  scope: {'ALL PROJECTS (machine-wide)' if args.all_projects else 'current project only'}")
    if not args.all_projects:
        print(f"  project slug: {project_slug}")
    if args.weeks:
        print(f"  window: last {args.weeks} week(s)")
    print(f"  privacy boundary (WFT-40a): counts/tiers/durations/tokens only — no prompt or output text is read or printed")
    print()

    project_dirs = discover_project_dirs(args.all_projects, project_slug)
    if not project_dirs:
        print("No transcript directory found in scope. Nothing to report.")
        if args.critique and args.all_projects:
            print("section 7 omitted: --critique is current-project only (WFT-101)")
        return 0

    records = collect_records(project_dirs, args.weeks)

    section_token_share(records, args.top_projects if args.all_projects else None)
    section_agent_counts(records)

    detector = find_tier_scan(repo_root)
    workflow_agg = section_workflow_coverage(project_dirs, detector, args.weeks)

    section_mis_tier(records)

    section_gate_health(repo_root, workflow_agg)

    section_coverage_gaps()

    if args.critique:
        if args.all_projects:
            print("section 7 omitted: --critique is current-project only (WFT-101)")
        else:
            build_critique_packet(project_dirs, detector, args.weeks, repo_root, project_slug)

    return 0


def find_repo_root():
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=5)
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    # scripts/ -> routing-audit/ -> skills/ -> .claude/ -> repo root
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, "..", "..", "..", ".."))


if __name__ == "__main__":
    sys.exit(main())
