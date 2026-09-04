# Open Questions

> Unresolved items surfaced by the 2026-09-04 kickoff transcript. Client's own disclaimer: the transcript may be inaccurate — do not build against any item here until Anton confirms. When resolved, move to `decisions.md`.

## OQ-1 — Resume format: text or file? (priority: HIGH)
**Question:** Original discovery assumed resume arrives as plain text. Transcript (Тема 3): "просто скинуть текст вакансии и файл резюме" — resume is a **file**. Which formats (PDF / DOCX / scanned image requiring OCR)?
**Why it matters:** Changes the tool list — a text-extraction step is needed that wasn't scoped. OCR is a materially bigger scope than PDF/DOCX text extraction.
**Next step:** Ask Anton directly; get 2-3 real sample resume files in their actual format.

## OQ-2 — Education requirement, exact meaning (priority: MEDIUM, was HIGH)
**Question:** Transcript Тема 2: "Наличие высшего образования, желательно не совпадающего с требуемым опытом работы." Two readings: (a) higher education itself is a required/scored criterion; (b) this is the date-overlap red flag (education years vs work-experience years must not overlap) restated.
**Why it matters:** (a) and (b) are different logic — (a) is a fit criterion, (b) is a fabrication red flag. Building the wrong one produces a card that misreads candidates.
**Working resolution (Ralina, 2026-09-04):** not either/or — both apply. (a) higher education present = green flag; (b) date overlap = red flag, already captured separately in `candidate-screening-criteria.md` section 2. Downgraded from blocking to needs-confirmation: proceeding with this reading in the prototype, sent to Anton for sign-off in `communications/2026-09-04-screening-criteria-for-approval.md`.
**Next step:** Wait for Anton's confirmation/correction; if he rejects the green-flag reading, drop it without re-litigating the red-flag half (that part was never in question).

## OQ-3 — "Contact check on opening" (priority: MEDIUM)
**Question:** Тема 5: "Поднят вопрос о необходимости проверки контактов в резюме при открытии." Unclear whether this means (a) validating the candidate's contact info (phone/email format, reachability), or (b) a file-safety check when opening an untrusted resume file (relevant now that resume is a file, not text — a resume could carry malicious content).
**Why it matters:** (b) is a guardrail/security requirement (untrusted file handling); (a) is a data-quality check. Different owners, different effort.
**Next step:** Confirm with Anton; if (b), route through the harness guardrails review for untrusted-file handling.

## OQ-4 — "Company-only visibility" (priority: MEDIUM)
**Question:** Тема 5: "Отмечена важность обеспечения видимости только компании в процессе работы." Unclear scope — likely tied to OQ-5 (hh.ru personal-account login): when the agent operates under a personal hh.ru account, should it be restricted to that company's own vacancies/candidates only, not the rest of the personal account's data?
**Why it matters:** Affects the access-scoping design for the hh.ru integration; a wrong guess here risks the agent touching data it shouldn't.
**Next step:** Confirm with Anton alongside OQ-5.

## OQ-5 — hh.ru API access is blocking, not just the hidden-vacancy edge case (priority: HIGH — upgraded, blocking)
**Question:** Originally scoped as "does hidden/direct vacancies need personal-account login" (transcript Тема 7: "Вход на сайты типа HeadHunter осуществляется через личный аккаунт пользователя"). **Escalated by D-9 (2026-09-04):** live testing found `api.hh.ru/vacancies` and `/vacancies/{id}` both return 403 for ANY unauthorized request, per hh.ru's April 2026 policy change closing public API access entirely. This means even the plain "public vacancy, no login" path this MVP was scoped around does not work today without a registered hh.ru API application.
**Why it matters:** This isn't a phase-2/nice-to-have anymore — the hh.ru-link input path is non-functional right now. Two separate questions bundled here: (1) does the company have a registered hh.ru API app / employer account with API access at all (needed for ANY vacancy fetch by link), and (2) if only a personal login is available, using it is still a guardrail Mentor Review trigger (personal authorized browser session, per harness playbook 08 — Guardrails & Security) independent of (1).
**Current workaround (shipped):** `vacancy.py` accepts pasted vacancy text as a fully-supported alternative to a link — this is not a fallback bug-path, it's the only working input method for vacancies until (1) is answered. The bot gives a clear error (not a crash) when a link 403s.
**Next step:** Ask Anton directly: does the company have (or can register) an official hh.ru employer API app? If yes, wire OAuth client credentials once received. If no realistic path, the link-input feature stays permanently text-only and that should be set as an explicit expectation, not a temporary gap. Do not build personal-login scraping regardless of the answer to (1) — see anti-stories.md.

## OQ-6 — What exactly are the "5 stages" of the process (priority: LOW)
**Question:** Transcript (Тема 1) states the screening process has 5 stages but does not enumerate them beyond what's inferred from Тема 3 (compare -> flag -> output -> recommend -> verdict).
**Why it matters:** Low priority because the requirements doc already captures the functional pieces; this is about confirming the client's own mental model matches ours, per discovery methodology (return understanding for confirmation).
**Next step:** State our inferred 5 stages back to Anton in the approval message and let him correct the count/order if wrong.
