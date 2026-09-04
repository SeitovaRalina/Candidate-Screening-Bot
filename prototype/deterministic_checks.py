"""Red flags computed in code, not left to LLM judgment.

Rationale: .memory-bank/tech-details/stack.md — "prove it with code, not
words" (Evals & Verification playbook chapter). Date-overlap and lexical
pattern checks are exactly the kind of thing an LLM can miss or hallucinate
about inconsistently across runs; a regex/date-math check is deterministic
and reproducible instead.

Honesty note: resumes are unstructured free text, so date extraction here is
a heuristic, not a parser for a known schema. It works on the common
"YYYY — YYYY" / "YYYY - н.в." patterns seen in RU/EN resumes and will miss
unusual formats. False negatives are expected and acceptable (the LLM step
still does its own read of the whole resume); false positives are mitigated
by always attaching the matched snippet as evidence so a human can dismiss a
wrong flag at a glance.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from models import Flag

_SECTION_HEADERS = {
    "education": [
        r"образовани[ея]", r"education", r"учеба", r"учёба",
    ],
    "experience": [
        r"опыт\s+работы", r"опыт", r"стаж", r"work\s+experience", r"experience",
        r"места\s+работы", r"карьера",
    ],
}

_YEAR_RANGE_RE = re.compile(
    r"(?P<start>(19|20)\d{2})\s*(?:г\.?)?\s*[-–—]\s*"
    r"(?:(?P<end>(19|20)\d{2})|(?P<present>наст\.?\s*время|н\.?в\.?|present|now|current))",
    re.IGNORECASE,
)

CURRENT_YEAR = 2026  # keep in sync with the environment's "today" — see CLAUDE.md currentDate


@dataclass
class YearRange:
    start: int
    end: int  # CURRENT_YEAR if "по настоящее время"
    snippet: str


def _split_sections(text: str) -> dict[str, str]:
    """Best-effort split by known headers. Falls back to treating the whole
    text as both sections if no headers are found — better to over-check than
    to silently skip the analysis on an unusual resume layout.
    """
    lines = text.splitlines()
    sections: dict[str, list[str]] = {"education": [], "experience": [], "_other": []}
    current = "_other"
    header_patterns = {
        name: re.compile(rf"^\s*(?:{'|'.join(pats)})\s*:?\s*$", re.IGNORECASE)
        for name, pats in _SECTION_HEADERS.items()
    }
    for line in lines:
        matched_header = False
        for name, pattern in header_patterns.items():
            if pattern.match(line.strip()):
                current = name
                matched_header = True
                break
        if not matched_header:
            sections[current].append(line)

    joined = {k: "\n".join(v) for k, v in sections.items()}
    if not joined["education"] and not joined["experience"]:
        # No recognizable headers at all — check the whole document for both.
        return {"education": text, "experience": text}
    return joined


def _extract_year_ranges(section_text: str) -> list[YearRange]:
    ranges: list[YearRange] = []
    for match in _YEAR_RANGE_RE.finditer(section_text):
        start = int(match.group("start"))
        end = int(match.group("end")) if match.group("end") else CURRENT_YEAR
        ranges.append(YearRange(start=start, end=end, snippet=match.group(0)))
    return ranges


def check_education_work_overlap(resume_text: str) -> list[Flag]:
    sections = _split_sections(resume_text)
    edu_ranges = _extract_year_ranges(sections["education"])
    work_ranges = _extract_year_ranges(sections["experience"])

    flags: list[Flag] = []
    for edu in edu_ranges:
        for work in work_ranges:
            # Flag when full-time work clearly starts before education ends
            # (more than a 1-year cushion, to avoid flagging ordinary
            # internships/part-time work during the final year of study).
            if work.start < edu.end - 1:
                flags.append(
                    Flag(
                        text=(
                            f"Работа ({work.snippet}) начинается раньше окончания обучения "
                            f"({edu.snippet}) — возможное пересечение дат"
                        ),
                        quote=f"{edu.snippet} ... {work.snippet}",
                        source="deterministic",
                    )
                )
    return flags


def check_employer_date_overlap(resume_text: str) -> list[Flag]:
    sections = _split_sections(resume_text)
    work_ranges = _extract_year_ranges(sections["experience"])
    flags: list[Flag] = []
    for i, a in enumerate(work_ranges):
        for b in work_ranges[i + 1 :]:
            overlap = min(a.end, b.end) - max(a.start, b.start)
            if overlap > 1:  # more than a 1-year cushion for reporting-period rounding
                flags.append(
                    Flag(
                        text=f"Пересекающиеся периоды работы: {a.snippet} и {b.snippet}",
                        quote=f"{a.snippet} / {b.snippet}",
                        source="deterministic",
                    )
                )
    return flags


def check_unexplained_gaps(resume_text: str, *, min_gap_years: int = 1) -> list[Flag]:
    """Year-level granularity only — can't reliably detect gaps under ~1 year
    from resume text alone, so this deliberately under-reports short gaps
    rather than guessing at month precision it doesn't have.
    """
    sections = _split_sections(resume_text)
    work_ranges = sorted(_extract_year_ranges(sections["experience"]), key=lambda r: r.start)
    flags: list[Flag] = []
    for prev, curr in zip(work_ranges, work_ranges[1:]):
        gap = curr.start - prev.end
        if gap >= min_gap_years:
            flags.append(
                Flag(
                    text=f"Необъяснённый перерыв в занятости (~{gap} г.) между {prev.snippet} и {curr.snippet}",
                    quote=f"{prev.snippet} ... {curr.snippet}",
                    source="deterministic",
                )
            )
    return flags


_AI_BUZZWORDS = [
    "spearheaded", "leveraged", "pivotal", "intricate", "showcasing", "synergy",
    "delve", "realm", "robust", "results-driven", "cutting-edge", "seamless",
    "результативн", "нацелен на результат", "синерг", "проактивн", "стрессоустойчив",
]


def check_ai_generated_text_pattern(resume_text: str) -> list[Flag]:
    """Lexical heuristic, not a verdict on honesty by itself — see
    .memory-bank/product-overview/requirements/candidate-screening-criteria.md
    section 2 "Lexical / near-deterministic" for why this must never be an
    automatic reject: AI-assisted editing of real content is now normal.
    """
    lower = resume_text.lower()
    hits = [word for word in _AI_BUZZWORDS if word in lower]

    word_count = max(len(resume_text.split()), 1)
    em_dash_count = resume_text.count("—") + resume_text.count("--")
    em_dash_rate = em_dash_count / word_count * 100

    flags: list[Flag] = []
    if len(hits) >= 3 or em_dash_rate > 1.5:
        example = next((w for w in hits), None)
        quote = (
            f"буквенные маркеры: {', '.join(hits[:5])}"
            if hits
            else f"частота тире: {em_dash_count} на {word_count} слов"
        )
        flags.append(
            Flag(
                text=(
                    "Признаки шаблонного/сгенерированного нейросетью текста — не повод для отказа "
                    "само по себе, но стоит присмотреться к конкретике достижений"
                ),
                quote=quote,
                source="deterministic",
            )
        )
    return flags


def run_all_deterministic_checks(resume_text: str) -> list[Flag]:
    return [
        *check_education_work_overlap(resume_text),
        *check_employer_date_overlap(resume_text),
        *check_unexplained_gaps(resume_text),
        *check_ai_generated_text_pattern(resume_text),
    ]
