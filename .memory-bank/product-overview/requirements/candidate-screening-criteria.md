# Candidate Screening Criteria

Sources: kickoff meeting transcript (2026-09-04, Anton + Ralina) + broader web research on universal resume-screening frameworks, recruiter red/green-flag checklists, and 2026-specific signals (AI-generated resume detection). The client explicitly asked for a universal framework, not just the handful of flags mentioned in the meeting — the meeting examples are a subset, marked `[from meeting]` below; everything else comes from market research and needs the client's sign-off before being treated as confirmed scope.

Card output uses a **green flags / red flags** structure (decided 2026-09-04, replacing separate "criteria" + "red flags" sections — see `vision.md`), each item carrying a resume quote as evidence.

## 1. Green flags — positive fit signals

### Vacancy match (deterministic-ish: field comparison)
- Must-have hard skills from the vacancy present in the resume, with description depth (not just a keyword mention).
- Seniority/grade in the resume's described responsibilities matches the vacancy's expected level.

### Quality signals (LLM judgment, evidence required)
- Quantified achievements per role (numbers, %, scale, timeframe) — CAR/STAR-style bullets ("increased X by Y%") score higher than vague claims ("significantly improved X").
- Career progression across roles: promotions, growing scope, team size, or budget over time.
- Concrete, specific project descriptions naming the actual technologies/tools used, not generic duty lists.
- For technical roles: verifiable public work (GitHub, portfolio, publications) referenced in the resume.
- Relevant certifications for the role.
- Higher education present (degree completed) — standalone green flag, separate from the date-overlap red flag in section 2. Working assumption (Ralina, 2026-09-04), pending Anton's confirmation.

## 2. Red flags — authenticity / fabrication signals

### Deterministic (compute from parsed dates/fields — do not leave to the LLM)
- Overlapping dates between education end and start of full-time work experience `[from meeting]`.
- Overlapping/conflicting dates between two employers with no "concurrent/side project" note.
- Long unexplained employment gap (commonly used threshold: >6 months with no note in the resume).

### Lexical / near-deterministic (simple text heuristics, cheaper and more consistent than pure LLM judgment)
- AI-generated/templated text markers — buzzword density (e.g. "spearheaded," "leveraged," "synergy," "delve," "robust," "results-driven"), unusually high em-dash frequency, or a tone that reads uniformly polished across every section. This does not by itself mean the candidate is dishonest (AI-assisted editing of real content is now common and not inherently a red flag) — but combined with generic, non-specific claims, it's a signal to look closer rather than take achievement claims at face value.

### Requires LLM judgment (evidence quote required)
- Title inflation: job title doesn't match the described responsibilities.
- Tech-stack mismatch: a long list of technologies in the skills header with no corresponding depth in the experience section `[from meeting]`.
- Job-hopping pattern: multiple consecutive roles under ~6 months with no stated reason (context-dependent — normal for some freelance/contract profiles, so this must be a flag-for-review, not an automatic reject).
- Vague, buzzword-only achievement claims with no concrete metric, technology, or outcome.
- Irrelevant or unprofessional content in a section where professional information is expected `[from meeting, client's own example]`.

## 3. Red flags — fit mismatch (vacancy-specific, not about honesty)

- Missing one or more must-have hard skills.
- Overqualification signal: candidate's demonstrated seniority/scope clearly exceeds the vacancy level — worth flagging for the recruiter as a retention-risk/salary-mismatch conversation topic, not a rejection reason by itself.
- Underqualification: gap between required and demonstrated seniority is large enough that a technical interview would likely be premature.

## 4. Education requirement `[NEEDS CONFIRMATION — see open-questions.md OQ-2]`

Meeting transcript: "Наличие высшего образования, желательно не совпадающего с требуемым опытом работы." Resolved as **both** readings, not either/or: (a) higher education present = green flag (section 1), (b) date overlap between education and work = red flag (section 2, already captured). Working assumption (Ralina, 2026-09-04) — still needs Anton's sign-off before being final, since it adds a green-flag criterion that wasn't explicit in the transcript.

## 5. Expected bot output

1. Verdict: fit / not fit, invite to technical interview or not.
2. Green flags / red flags list, each with a resume quote as evidence.
3. Recommended interview questions — targeted at the specific gaps and red flags found for this candidate, not a generic question bank.

## 6. Human-in-the-loop

The bot runs the green/red-flag analysis autonomously. The final invite/reject decision stays with the recruiter — see `steerings/project-rules.md` and D-3 in `.assistant/decisions.md`.

## Open items

See `.assistant/open-questions.md` for items this criteria set does not resolve on its own (resume format, hh.ru scope, statelessness/retention, batch input).
