"""Unit tests for code-computed red flags.

These use synthetic resume text, not the client's real cases (Anton still
owes us 5 real resume+vacancy pairs per communications/2026-09-04-kickoff-followup.md
item 7) - once those arrive, add them here as the real acceptance set per
.memory-bank/tech-details/stack.md's evals section (obvious fit / obvious
no-fit / borderline / fabricated-experience / date-overlap).
"""
from deterministic_checks import (
    check_ai_generated_text_pattern,
    check_education_work_overlap,
    check_employer_date_overlap,
    check_unexplained_gaps,
)

RESUME_WITH_DATE_OVERLAP = """
Иванов Иван

Образование
МГУ, факультет ВМК
2015 - 2020

Опыт работы
ООО Ромашка, разработчик
2018 - 2022
"""

RESUME_CLEAN = """
Иванов Иван

Образование
МГУ, факультет ВМК
2015 - 2020

Опыт работы
ООО Ромашка, разработчик
2020 - 2022

ООО Лютик, старший разработчик
2022 - н.в.
"""

RESUME_WITH_EMPLOYER_OVERLAP = """
Опыт работы
Компания А
2018 - 2021

Компания Б
2019 - 2023
"""

RESUME_WITH_GAP = """
Опыт работы
Компания А
2015 - 2017

Компания Б
2020 - 2023
"""

RESUME_AI_GENERATED_STYLE = (
    "Результативный специалист — с проактивным подходом — spearheaded ключевые проекты — "
    "leveraged synergy между командами — showcasing intricate знания в своей области."
)


def test_detects_education_work_overlap():
    flags = check_education_work_overlap(RESUME_WITH_DATE_OVERLAP)
    assert len(flags) == 1
    assert "2018" in flags[0].quote


def test_no_false_positive_on_clean_resume():
    assert check_education_work_overlap(RESUME_CLEAN) == []
    assert check_employer_date_overlap(RESUME_CLEAN) == []
    assert check_unexplained_gaps(RESUME_CLEAN) == []


def test_detects_employer_date_overlap():
    flags = check_employer_date_overlap(RESUME_WITH_EMPLOYER_OVERLAP)
    assert len(flags) == 1


def test_detects_unexplained_gap():
    flags = check_unexplained_gaps(RESUME_WITH_GAP)
    assert len(flags) == 1
    assert "перерыв" in flags[0].text.lower()


def test_detects_ai_generated_style():
    flags = check_ai_generated_text_pattern(RESUME_AI_GENERATED_STYLE)
    assert len(flags) == 1
    assert flags[0].source == "deterministic"


def test_no_ai_flag_on_normal_text():
    normal = "Разрабатывал backend на Python, внедрил очередь задач на Celery, сократил время ответа API на 30%."
    assert check_ai_generated_text_pattern(normal) == []


def test_no_ai_flag_on_em_dash_date_ranges():
    """Regression: em-dashes used as "2020 — 2024" date separators (the more
    common RU-resume convention than a plain hyphen, unlike the fixtures
    above) must not count toward the dash-density signal by themselves -
    found via prototype/tests/manual_cases while building self-sourced test
    pairs, see .assistant/decisions.md D-18.
    """
    resume = (
        "Образование\nМГУ, ВМК\n2016 — 2021\n\n"
        "Опыт работы\nООО Ромашка\n2021 — н.в.\n\n"
        "ООО Лютик\n2019 — 2021\n"
    )
    assert check_ai_generated_text_pattern(resume) == []
