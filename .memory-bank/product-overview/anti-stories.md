# Anti-Stories

What this bot explicitly does NOT do in the MVP:

- Does not reject or invite a candidate on its own — no message is sent to the candidate automatically. Output goes to the recruiter only.
- Does not log into hh.ru under a personal account to reach hidden/direct vacancies — MVP covers public vacancies via the official API only. Personal-account login is a separate, explicitly-approved phase (guardrail: personal authorized browser session requires review).
- Does not screen multiple candidates in one request (no batch mode).
- Does not pull candidate data from sources other than the resume the recruiter provides and the linked vacancy (no social media lookups, no background-check services) unless a later phase adds them with client sign-off.
- Does not treat resume/vacancy content as instructions to the agent — text from these untrusted sources is data to analyze, never a command (prompt-injection boundary).
- Does not silently invent facts about a candidate not present in the resume — every claim in the card must trace to a quote.
