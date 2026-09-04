from card import render_card
from models import CandidateCard, Flag


def test_render_card_includes_evidence_and_disclaimer():
    card = CandidateCard(
        verdict="fit",
        invite_to_interview=True,
        green_flags=[Flag(text="Есть опыт с Python", quote="5 лет на Python в бэкенде")],
        red_flags=[Flag(text="Пересечение дат", quote="2018 - 2022 / 2020 - 2020", source="deterministic")],
        interview_questions=["Расскажите про самый сложный проект на Python"],
    )
    text = render_card(card)

    assert "Подходит" in text
    assert "5 лет на Python в бэкенде" in text
    assert "🔧" in text  # deterministic flag marker (not "[code]" - see card.py)
    assert "Финальное решение — за вами" in text


def test_render_card_handles_empty_flags():
    card = CandidateCard(
        verdict="unclear",
        invite_to_interview=False,
        green_flags=[],
        red_flags=[],
        interview_questions=[],
    )
    text = render_card(card)
    assert "нет" in text
