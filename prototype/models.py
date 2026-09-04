"""Shared data types for the candidate screening pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Flag:
    """One green or red flag with the resume/vacancy quote backing it.

    `source` distinguishes a flag computed deterministically in code from one
    the LLM judged, so the card can be honest about which is which — see
    .memory-bank/tech-details/stack.md "prove it with code, not words".
    """

    text: str
    quote: str
    source: str = "llm"  # "llm" | "deterministic"


@dataclass
class VacancyInfo:
    title: str
    description: str
    key_skills: list[str] = field(default_factory=list)
    experience: str | None = None
    source_url: str | None = None


@dataclass
class CandidateCard:
    verdict: str  # "fit" | "not_fit" | "unclear"
    invite_to_interview: bool
    green_flags: list[Flag]
    red_flags: list[Flag]
    interview_questions: list[str]
