# Existing Solutions (market scan, 2026-09-04)

## RU market (relevant — client sources vacancies from hh.ru)
- **Talantix** — ATS built by the hh.ru team. Direct architectural reference.
- **Skillaz** — already ships automatic AI resume scoring against configured criteria + a recruiter assistant; closest existing product to what the client is asking for. Worth showing to the client as a UX reference point.
- **Huntflow** — leading RU/CIS recruiting CRM; candidate database + history + reporting, less focus on AI scoring specifically.

## International commercial
- Hire-Match, CVViZ, Truffle, HaiTalent — parse + score + rank resumes against a job description; none foreground a "fabrication/red-flag" check as a first-class feature, that part is still manual for recruiters industry-wide.

## Open source (architecture reference, not for direct reuse)
- **Resume-Matcher** — resume vs JD comparison, gap analysis, supports 100+ LLMs including Anthropic.
- **candisift** — explicitly "bias-audited ranking" — relevant precedent for taking ranking bias seriously.
- **skillmatch-ai** — positions itself as explainable + privacy-first CV matching — directly matches this client's "don't blindly trust the AI" requirement; explainability should be designed in from the start, not bolted on.

## Compliance note (relevant to the human-in-the-loop rule in project-rules.md)

US EEOC enforcement precedent (iTutorGroup case: fined for an AI tool that auto-rejected candidates by age) establishes that the employer carries liability for algorithmic bias, not the tool vendor, and regulators expect human validation before a final hiring decision. This directly backs the project rule that the bot's verdict must stay advisory with the recruiter making the final call — worth surfacing to the client as external validation, not just an internal constraint.

Sources: https://sapia.ai/resources/blog/resume-screening-software/, https://hh.ru/article/ne-teryajte-silnyh-kandidatov-v-potoke-otklikov, https://hrlead.ru/solutions/ats/talantix/, https://github.com/topics/resume-matcher, https://www.workforcebulletin.com/ai-resume-screening-tool-developer-is-subject-to-federal-anti-discrimination-laws-says-eeoc
