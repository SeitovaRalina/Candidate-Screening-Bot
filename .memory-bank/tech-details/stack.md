# Stack

Rationale follows the Effective Agent Engineering Playbook decision trees (channel → harness → tools → knowledge → guardrails → evals).

## Architecture shape

Workflow with LLM reasoning steps, not a freely-exploring autonomous agent — the path is known in advance (parse vacancy -> parse resume -> compare -> deterministic date checks -> LLM red-flag/fit judgment -> assemble card). Called "agent" to the client in the everyday sense (AI-powered bot); internally it is a managed pipeline, which matters for how it's evaluated (deterministic checks + rubric, not "did the agent figure it out").

## Channel
**Hermes Messaging Gateway -> Telegram.** Do not hand-roll a Telegram bot loop; Hermes already handles the channel, attachments (needed now that resume arrives as a file, not just text), and session restart.

## Runtime / harness
**Hermes Agent**, not LangGraph. No requirement for multi-day pause/resume or checkpointed state machine on MVP — one request in, one card out, synchronous.

## Tools
- hh.ru vacancy: the **public vacancy webpage's embedded JSON-LD** (`https://hh.ru/vacancy/{id}`, `schema.org/JobPosting` block), not `api.hh.ru` — the latter closed unauthorized access in April 2026 (D-9), verified live. The public page has no such gate (200, no login, not disallowed by robots.txt) and embeds structured data meant for search-engine indexing, which is parsed directly (D-10). Confirmed end-to-end against a real live vacancy. Hidden/direct vacancies are not reachable this way — that narrower case is still open (OQ-5).
- hh.ru hidden/direct vacancies (personal-account login): **not built in MVP** — flagged as a guardrail/legal open item (see `.assistant/open-questions.md`). If approved later: Playwright (scenario is known: page -> field -> result), not Browser Use.
- Resume file ingestion: needs a parsing step (PDF/DOCX -> text) that the original architecture (resume-as-text) did not account for — confirm supported formats with Anton, then add a straightforward extraction tool (e.g. a PDF/DOCX text-extraction library called from a Skill), not a custom OCR pipeline unless scanned images are confirmed in scope.
- Deterministic red-flag checks (date overlaps) implemented in plain code, not left to the LLM — see Evals principle "prove it with code, not words."

## Roles / multi-agent
**Single agent**, steps expressed as Skills: parse vacancy, parse resume, structured comparison, deterministic date checks, build candidate card. No case for subagents/multi-agent at this scope (no parallel independent subtasks, no need for permission isolation).

## Knowledge
Small, static knowledge file (`.memory-bank/product-overview/requirements/candidate-screening-criteria.md`) given to the agent as context/Skill input. No RAG/vector DB — this is one rubric document, not a large or frequently-changing corpus.

## Guardrails
- hh.ru API call: READ, automatic.
- Sending the card to Telegram: WRITE REVERSIBLE, automatic + logged.
- Final hiring decision: DANGEROUS tier by default (human approval) — bot output is a recommendation only.
- Resume/vacancy text: untrusted content, never treated as instructions to the agent.
- Candidate PII: no plaintext resume content in logs beyond what's operationally necessary; secrets (Telegram token, any hh.ru credentials) via env vars/secret manager, never in prompt or repo.

## Verification
Small project -> pytest / plain scripts against a fixed case set (see acceptance criteria), not Langfuse/LangSmith at this scale. Minimum 5 real cases from the client covering: clear fit, clear no-fit, borderline, fabricated-experience red flag, date-overlap red flag. Deterministic checks asserted by code; LLM-judgment parts scored by rubric; re-run each case 3x (pass^k) since a hiring-adjacent judgment that flips between runs is a failure even if one run was correct.
