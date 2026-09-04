"""Unit tests for bot.py's pure-function helpers (small-talk detection,
combined-message splitting). Not testing the Telegram handlers themselves -
that needs a python-telegram-bot Update/Context double and isn't worth
building for logic this small; these functions take/return plain
strings/tuples so they're testable directly.
"""
from bot import _detect_kind, _looks_like_off_topic, _looks_like_small_talk, _try_split_combined_message


# --- _detect_kind (D-25: content-based routing, order-independent input) ---

_RESUME_WITH_HEADER = (
    "Смирнов Дмитрий Олегович\nMiddle Python-разработчик\n\n"
    "Опыт работы:\n2022 - н.в., Senior Python Developer, ООО \"Финтех Решения\""
)


def test_hh_link_detected_as_vacancy():
    assert _detect_kind("https://hh.ru/vacancy/133660218") == "vacancy"


def test_resume_with_header_detected_as_resume():
    assert _detect_kind(_RESUME_WITH_HEADER) == "resume"


def test_vacancy_marker_text_detected_as_vacancy():
    assert _detect_kind("Ищем Python-разработчика, требования: Django, з/п по итогам собеседования") == "vacancy"


def test_marker_free_text_is_ambiguous():
    assert _detect_kind("Python разработчик, удалёнка, полная занятость") == "ambiguous"


def test_unrelated_question_is_off_topic():
    assert _looks_like_off_topic("А ты вообще ИИ?") is True
    assert _looks_like_off_topic("Какая сегодня погода?") is True


def test_real_vacancy_text_is_not_off_topic():
    assert _looks_like_off_topic("Ищем Python-разработчика, требования: Django, опыт от 2 лет") is False


def test_hh_link_is_not_off_topic():
    assert _looks_like_off_topic("https://hh.ru/vacancy/130056956") is False


def test_greeting_plus_question_is_small_talk():
    assert _looks_like_small_talk("Привет! Что ты можешь?") is True


def test_bare_greeting_is_small_talk():
    assert _looks_like_small_talk("привет") is True
    assert _looks_like_small_talk("hi") is True


def test_hh_link_is_not_small_talk():
    assert _looks_like_small_talk("https://hh.ru/vacancy/130056956") is False


def test_pasted_vacancy_text_is_not_small_talk():
    text = "Python-разработчик, опыт 3 года, требуется знание Django и PostgreSQL"
    assert _looks_like_small_talk(text) is False


def test_long_text_never_counts_as_small_talk_even_with_a_greeting_word():
    # A pasted resume/vacancy could plausibly contain "hi" as a substring
    # inside an unrelated word; the length cap is the actual safety net here,
    # word-boundary tokenizing on its own would still miss e.g. "hi-tech".
    long_text = "Опыт работы в hi-tech компании. " * 5
    assert _looks_like_small_talk(long_text) is False


# --- _try_split_combined_message (D-22: single-message vacancy+resume input) ---

_COMBINED_VACANCY_THEN_RESUME = (
    "Вакансия: Python-разработчик. Требования: Django, PostgreSQL, 3+ года опыта.\n\n"
    "Опыт работы:\n2020 - 2024, ООО Ромашка, backend-разработчик, много всего "
    "интересного делал тут за эти годы."
)

_COMBINED_HH_LINK_THEN_FREEFORM_RESUME = (
    "https://hh.ru/vacancy/130056956 Иванов Иван, программист, работал в разных "
    "компаниях много лет, увлекаюсь опенсорсом и своими проектами на гитхабе, "
    "ищу интересные задачи и сильную команду."
)

_PURE_RESUME_ALONE = (
    "Иванов Иван Иванович\nemail@example.com\n\nОбразование:\nМГУ 2016-2021\n\n"
    "Опыт работы:\n2021 - н.в., Python разработчик, ООО Ромашка"
)

_PURE_VACANCY_ALONE = "Ищем Python-разработчика с опытом Django от 2 лет, зарплата от 150000."


def test_splits_vacancy_marker_then_resume_section():
    result = _try_split_combined_message(_COMBINED_VACANCY_THEN_RESUME)
    assert result is not None
    vacancy_part, resume_part = result
    assert "Требования" in vacancy_part
    assert vacancy_part.startswith("Вакансия")
    assert resume_part.startswith("Опыт работы")


def test_splits_hh_link_then_freeform_resume_with_full_link_no_leftover_scheme():
    result = _try_split_combined_message(_COMBINED_HH_LINK_THEN_FREEFORM_RESUME)
    assert result is not None
    vacancy_part, resume_part = result
    assert vacancy_part == "https://hh.ru/vacancy/130056956"
    assert "https://" not in resume_part  # regression: scheme must not leak into the resume half
    assert resume_part.startswith("Иванов")


def test_does_not_split_a_resume_sent_alone():
    # No vacancy-marker keyword before "Опыт работы" - must not carve off the
    # name/education block as a fake "vacancy".
    assert _try_split_combined_message(_PURE_RESUME_ALONE) is None


def test_does_not_split_a_vacancy_sent_alone():
    assert _try_split_combined_message(_PURE_VACANCY_ALONE) is None
