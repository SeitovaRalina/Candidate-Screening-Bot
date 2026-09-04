"""Unit tests for screening.py's pure post-processing helpers.

Not testing screen_candidate() itself - that needs a real ANTHROPIC_API_KEY
and hits the live LLM gateway (see README.md). These two functions were
extracted specifically because they're the fix for two bugs Ralina found in
manual testing (2026-09-04, D-27): fake "quote": "нет" placeholders passed
off as evidence, and interview_questions items coming back as
{"text": ...} dicts instead of plain strings.
"""
from models import Flag
from screening import _as_question_text, _has_real_quote


def test_real_quote_is_kept():
    assert _has_real_quote(Flag(text="x", quote="Разработка REST API на FastAPI")) is True


def test_fake_quote_variants_are_rejected():
    for fake in ("нет", "НЕТ", "  нет  ", "", "   ", "n/a", "-"):
        assert _has_real_quote(Flag(text="x", quote=fake)) is False


def test_plain_string_question_passes_through():
    assert _as_question_text("Расскажите про свой опыт с asyncio") == "Расскажите про свой опыт с asyncio"


def test_dict_shaped_question_is_coerced_to_its_text():
    assert _as_question_text({"text": "Расскажите про опыт с RAG"}) == "Расскажите про опыт с RAG"


def test_dict_without_text_key_does_not_crash():
    # Defensive fallback - str() of the dict itself, not a KeyError. Ugly is
    # acceptable here; a crash mid-screening is not.
    result = _as_question_text({"question": "Как вы тестируете код?"})
    assert result == "Как вы тестируете код?"
