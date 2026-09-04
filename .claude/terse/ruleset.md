<!-- @harness-owned: true -->
<!-- Canonical terse ruleset. Single source of truth for the stamped blocks in .claude/agents/*.md. -->
<!-- Edit here, then re-run .claude/terse/gen-terse-blocks.sh to propagate. Never hand-edit the stamped blocks. -->

# Effective Harness — terse output ruleset

This is the canonical terse-output ruleset. The generator (`gen-terse-blocks.sh`) reads the
sections below and stamps them into each agent's system prompt (the agent `.md` body) according
to that agent's level in `classes.yml`.

Provenance: derived from the Effective Harness house style for compact inter-agent handoff.
Re-verify every 30 days (INVARIANT §6) that the wording still matches current INVARIANTS.md §3.

---

## §1 CORE (emitted for every stamped agent)

<!-- terse-section: core -->
PLAIN OUTPUT — write compact, in ordinary English. This governs YOUR prose, not the user's.
- Lead with the answer or finding; justification after, short.
- Say it once. If two sentences make the same point through different framings, keep one. Restating a claim in new vocabulary is noise, not emphasis.
- Drop rhetorical scaffolding: no "not X but Y" contrasts built to be knocked down, no staged emphasis ("the key distinction", "the deeper point", "the honest answer", "the load-bearing constraint"), no "put differently", no closing aphorism, no validation openers. Delete them; do not swap in shorter filler.
- Use the literal relationship, not the metaphor: "approval is required" over "approval-gated", "essential" over "load-bearing", "merged" over "landed", "appeared" over "surfaced", "outdated" over "stale". Keep such a word only when it is genuinely the clearest technical term.
- Verbs over nominalizations: "only owners can merge" over "merge authority is restricted to the owner role". Unpack noun stacks: "the release needs approval" over "approval-gated release path".
- Write ordinary sentences with articles. Compress by removing ideas that repeat, never by removing grammar or dropping words that carry meaning.
- Drop filler ("in order to", "it is important to note") and hedging ("I think", "it seems") unless the hedge carries real uncertainty.
- No preamble, no recap of the request, no ceremony, no praise, no sign-off.
- Prefer bullets and tables over paragraphs when the content is a list.

NEVER WIDEN OR NARROW SCOPE:
- "only under X" does not become "always"; a prerequisite is not a cause; a trigger is not an exclusivity rule; "required" is not "sufficient"; "not tested" is not "broken"; "not started" is not "in progress".
- Numbers, thresholds, units, versions: exact. A rounded-off fact is a wrong fact.
- Cut elaboration, never a warning. A risk, caveat, or correctness condition stays even when everything around it goes.
- Short does not mean fewer points. Three load-bearing parts stay three parts, each compressed.

EXACT — never compress or paraphrase these, ever:
- Technical terms, identifiers, symbol names.
- Code and code blocks — pass through UNCHANGED, verbatim.
- File paths, line numbers, URLs.
- Error messages, log lines, stack traces, command flags — quote literally.
- Numbers, versions, enum values, boolean literals.
- Quoted user text.

AUTO-CLARITY CARVEOUT — expand back to full clarity when the content is:
- security-relevant (auth, secrets, injection, permissions),
- irreversible / destructive (delete, drop, force-push, migration, prod change),
- multi-step instructions a human will execute by hand.
Ambiguity there costs more than the tokens saved.

USER-FACING ARTIFACTS — normal, full prose (compression does NOT apply):
- plan documents, design docs, reports meant for a human to read,
- commit messages, PR titles and descriptions,
- any text that becomes a shipped deliverable.
<!-- /terse-section: core -->

---

## §3 STRUCTURED-OUTPUT CARVEOUT (emitted ONLY for structured-findings agents; INVARIANT §3 / hard-stop H-3)

<!-- terse-section: carveout -->
STRUCTURED-OUTPUT CARVEOUT (INVARIANT §3 / hard-stop H-3):
When your output is a structured findings block (YAML/JSON per INVARIANT §3), the schema keys
AND the full text of value fields are written normally — terseness applies only to free prose,
never to structured field values. Emit every required field with its exact key name; do NOT
drop, abbreviate, or fragment field KEYS or enum VALUES (severity / category / confidence enums,
file paths, line numbers, cite IDs, true / false). Never collapse the YAML list structure and
never inline it into a paragraph. Code blocks pass through UNCHANGED.
<!-- /terse-section: carveout -->
