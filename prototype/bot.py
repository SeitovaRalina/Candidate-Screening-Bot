"""Telegram bot handlers.

Strict two-step flow (D-21): vacancy first, resume second - not "any order".
An earlier "any order, two plain-text messages" design had no way to tell a
pasted resume from a pasted vacancy description (both are just "text"), so a
user sending them in the unexpected order got a silently wrong card instead
of an error. Fetching+confirming the vacancy immediately (before asking for
the resume) removes the ambiguity and gives the user visible proof of what
the bot understood at each step, instead of finding out only after the final
card comes back garbled.

Combined single-message input is also accepted (D-22): a user may reasonably
paste the vacancy and resume together in one message, or send the resume
file with the vacancy text as its caption, rather than as two sends. Both
are detected and screened immediately, without waiting for a second message.
See _try_split_combined_message()'s docstring for exactly how much this can
and can't tell apart - it is a best-effort heuristic split, not a classifier.

Per-chat pending state only pairs one candidate's vacancy+resume together
across two messages - it is cleared immediately after a card is produced.
This is NOT cross-candidate memory (see .assistant/open-questions.md OQ-3):
nothing about candidate N is available when screening candidate N+1.
"""
from __future__ import annotations

import asyncio
import logging
import re

from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, CommandHandler, filters

from config import LOCAL_DEBUG_LOGGING, PROXY_URL, TELEGRAM_BOT_TOKEN, require_config
from deterministic_checks import run_all_deterministic_checks
from resume_extract import ResumeExtractionError, extract_resume_text
from screening import ScreeningIncompleteError, screen_candidate
from card import render_card
from vacancy import VacancyFetchError, VacancyInfo, fetch_vacancy

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("candidate_screening_bot")

_EMPTY_PENDING = {"vacancy": None, "resume_text": None, "resume_file": None}

_START_MESSAGE = (
    "Привет! Я проверяю кандидата по вакансии в 2 шага:\n\n"
    "1️⃣ Сначала пришлите вакансию — ссылку на hh.ru или просто текст описания.\n"
    "2️⃣ Когда я приму вакансию, пришлите резюме кандидата — файлом (PDF/DOCX/TXT) или текстом.\n\n"
    "Можно и одним сообщением: вставьте вакансию и резюме вместе (или пришлите файл резюме "
    "с текстом вакансии в подписи к файлу) — я постараюсь разделить их сама.\n\n"
    "После этого соберу карточку кандидата с зелёными/красными флагами и вопросами для интервью."
)

_ASK_FOR_VACANCY = "Пришлите вакансию: ссылку на hh.ru или текст описания вакансии."
_ASK_FOR_RESUME = "Теперь пришлите резюме кандидата: файлом (PDF/DOCX/TXT) или текстом."

# Not an LLM intent classifier - this bot is a deterministic workflow (D-1),
# not a freely-conversational agent. This is a narrow, cheap keyword check for
# the "Привет, что ты умеешь?" case a client will predictably try during a
# demo before sending a real vacancy - not a general chit-chat handler.
_SMALL_TALK_PHRASES = ("что ты умеешь", "что ты можешь", "что умеешь", "что можешь", "как дела")
_SMALL_TALK_WORDS = {"привет", "здравствуй", "здравствуйте", "хай", "hello", "hi", "help", "помощь", "справка"}
_MAX_SMALL_TALK_LEN = 80  # a real pasted vacancy/resume is essentially never this short


def _looks_like_small_talk(text: str) -> bool:
    if len(text) > _MAX_SMALL_TALK_LEN:
        return False
    lower = text.lower()
    if any(phrase in lower for phrase in _SMALL_TALK_PHRASES):
        return True
    tokens = re.findall(r"[a-zа-яё]+", lower)
    return any(token in _SMALL_TALK_WORDS for token in tokens)


# Same "off-topic question" gap as small talk (D-20), but for any unrelated
# question rather than just a greeting - "какая сегодня погода?", "а ты
# вообще ИИ?" etc. would otherwise get silently swallowed as vacancy/resume
# text. Not an LLM classifier for the same reasons as _looks_like_small_talk:
# cheap, deterministic, no dependency on this session's flaky gateway.
_QUESTION_WORDS = ("что", "как", "почему", "зачем", "сколько", "когда", "кто", "где", "why", "what", "how")
_MAX_OFF_TOPIC_LEN = 150  # a real vacancy/resume paste is essentially never this short


def _looks_like_off_topic(text: str) -> bool:
    if len(text) > _MAX_OFF_TOPIC_LEN:
        return False
    lower = text.lower().strip()
    looks_like_a_question = lower.endswith("?") or lower.startswith(_QUESTION_WORDS)
    if not looks_like_a_question:
        return False
    has_vacancy_or_resume_marker = (
        _VACANCY_MARKER_RE.search(text) or _HH_LINK_SPAN_RE.search(text) or _RESUME_SECTION_RE.search(text)
    )
    return not has_vacancy_or_resume_marker


# Same section headers deterministic_checks.py already looks for in a resume
# - reusing that vocabulary instead of inventing a second one.
_RESUME_SECTION_RE = re.compile(r"(опыт\s+работы|места?\s+работы|резюме\s+кандидата)", re.IGNORECASE)
_VACANCY_MARKER_RE = re.compile(
    r"(вакансия|требовани|обязанност|з/?п\b|оклад|ищем|условия\s+работы)", re.IGNORECASE
)
# Full link span including an optional scheme, so a split never leaves a
# stray "https://" behind in the other half - vacancy.py's own _HH_URL_RE
# only captures "hh.ru/vacancy/<id>" (scheme-agnostic by design, since it
# only needs the id), which is right for that module but wrong for slicing
# text here.
_HH_LINK_SPAN_RE = re.compile(r"(?:https?://)?(?:www\.)?hh\.ru/vacancy/\d+", re.IGNORECASE)
_MIN_COMBINED_PART_LEN = 60  # below this a "part" is noise, not a real vacancy/resume


def _try_split_combined_message(text: str) -> tuple[str, str] | None:
    """Best-effort split for a single message that contains both the vacancy
    and the resume, instead of two separate sends.

    Not a classifier - deliberately conservative, and returns None (meaning
    "treat the whole message as just the vacancy", same as before this
    feature existed) whenever it isn't fairly confident, rather than risk
    silently mangling a legitimate single-item message. Two strategies, tried
    in order:

    1. A resume section header (see deterministic_checks.py's own patterns)
       appears after some vacancy-marker keyword ("вакансия", "требования",
       "оклад", ...) or an hh.ru link earlier in the text - split there.
       The vacancy-marker requirement exists specifically so a resume sent
       *alone* (its own "Образование"/contact block before "Опыт работы")
       doesn't get its header block wrongly carved off as a fake "vacancy".
    2. An hh.ru link is present and the remainder of the text (link removed)
       is long enough to plausibly be a whole resume on its own, even
       without a recognizable header - covers "<link> <freeform resume
       text>" pastes that skip a labeled section.

    Known blind spot: a resume that happens to mention a hiring-sounding word
    ("компания", "обязанности" as in "мои обязанности были...") before its
    own experience section could still misfire strategy 1. Acceptable for a
    same-day prototype; not silent data loss either way since both halves
    are still used as *something*, just possibly swapped - see D-22.
    """
    section_match = _RESUME_SECTION_RE.search(text)
    if section_match:
        before = text[: section_match.start()]
        after = text[section_match.start():].strip()
        has_vacancy_marker = _HH_LINK_SPAN_RE.search(before) or _VACANCY_MARKER_RE.search(before)
        before = before.strip()
        if has_vacancy_marker and len(before) >= _MIN_COMBINED_PART_LEN and len(after) >= _MIN_COMBINED_PART_LEN:
            return before, after

    hh_match = _HH_LINK_SPAN_RE.search(text)
    if hh_match:
        remainder = (text[: hh_match.start()] + text[hh_match.end():]).strip()
        if len(remainder) >= _MIN_COMBINED_PART_LEN * 2:  # more conservative without a header cue
            return text[hh_match.start() : hh_match.end()], remainder

    return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _reset_pending(context)
    await update.message.reply_text(_START_MESSAGE)


def _reset_pending(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.chat_data["pending"] = dict(_EMPTY_PENDING)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    pending = context.chat_data.setdefault("pending", dict(_EMPTY_PENDING))

    if pending["vacancy"] is None:
        await _handle_vacancy_step(message, context, pending)
        return

    await _handle_resume_step(message, context, pending)


async def _handle_vacancy_step(message, context: ContextTypes.DEFAULT_TYPE, pending: dict) -> None:
    # Combined case 1: resume file sent now, with the vacancy text as its
    # caption (D-22) - screen immediately instead of asking for a vacancy
    # the user already provided.
    if message.document and message.caption and not _looks_like_small_talk(message.caption.strip()):
        vacancy_text = message.caption.strip()
        try:
            vacancy = await fetch_vacancy(vacancy_text)
        except VacancyFetchError as exc:
            logger.warning("vacancy fetch failed (caption): %s", exc)
            await message.reply_text(f"Вакансия недоступна для парсинга.\n\nПодробности: {exc}")
            return
        tg_file = await message.document.get_file()
        data = await tg_file.download_as_bytearray()
        pending["vacancy"] = vacancy
        pending["resume_file"] = (bytes(data), message.document.file_name)
        await message.reply_text(
            f"✅ Вакансия принята: {vacancy.title}\nРезюме получено вместе с вакансией, обрабатываю..."
        )
        await _finalize_resume_and_screen(message, context, pending)
        return

    if message.document:
        await message.reply_text(f"Сначала вакансия, потом резюме. {_ASK_FOR_VACANCY}")
        return
    if not message.text:
        await message.reply_text(_ASK_FOR_VACANCY)
        return

    text = message.text.strip()
    if _looks_like_small_talk(text):
        await message.reply_text(_START_MESSAGE)
        return
    if _looks_like_off_topic(text):
        await message.reply_text(f"Я отвечаю только по задаче — проверка кандидата по вакансии. {_ASK_FOR_VACANCY}")
        return

    # Combined case 2: vacancy + resume pasted together as plain text (D-22).
    split = _try_split_combined_message(text)
    if split:
        vacancy_text, resume_text = split
        try:
            vacancy = await fetch_vacancy(vacancy_text)
        except VacancyFetchError as exc:
            logger.warning("vacancy fetch failed (combined message): %s", exc)
            await message.reply_text(f"Вакансия недоступна для парсинга.\n\nПодробности: {exc}")
            return
        pending["vacancy"] = vacancy
        pending["resume_text"] = resume_text
        await message.reply_text(
            f"✅ Вакансия принята: {vacancy.title}\nРезюме получено в этом же сообщении, обрабатываю..."
        )
        await _finalize_resume_and_screen(message, context, pending)
        return

    # A lone resume sent at this step (no vacancy marker before it, so
    # _try_split_combined_message above declined to split it) would otherwise
    # be silently accepted as "vacancy text" - vacancy.py has no validation,
    # it treats any string as a valid description. Caught live (2026-09-04):
    # Ralina sent a resume first, it became "the vacancy", then the real
    # hh.ru link sent next got treated as raw resume text instead of fetched,
    # and the LLM call on that garbled pair never produced a usable card.
    if _RESUME_SECTION_RE.search(text):
        await message.reply_text(
            f"Это похоже на резюме, а не на вакансию. {_ASK_FOR_VACANCY}\n\n"
            "(Если это всё же вакансия — переформулируйте без слов вроде "
            "\"опыт работы\"/\"место работы\", чтобы я не путала её с резюме.)"
        )
        return

    try:
        vacancy = await fetch_vacancy(text)
    except VacancyFetchError as exc:
        logger.warning("vacancy fetch failed: %s", exc)
        # Exact phrasing requested by Anton (reply to kickoff-followup.md item
        # 2): must lead with this line for any inaccessible/unparseable
        # vacancy, not a generic technical error.
        await message.reply_text(f"Вакансия недоступна для парсинга.\n\nПодробности: {exc}")
        return

    pending["vacancy"] = vacancy
    await message.reply_text(f"✅ Вакансия принята: {vacancy.title}\n\n{_ASK_FOR_RESUME}")


async def _handle_resume_step(message, context: ContextTypes.DEFAULT_TYPE, pending: dict) -> None:
    if message.document:
        tg_file = await message.document.get_file()
        data = await tg_file.download_as_bytearray()
        pending["resume_file"] = (bytes(data), message.document.file_name)
    elif message.text:
        text = message.text.strip()
        if _looks_like_small_talk(text) or _looks_like_off_topic(text):
            await message.reply_text(f"Я отвечаю только по задаче — проверка кандидата по вакансии. {_ASK_FOR_RESUME}")
            return
        # A bare hh.ru link here is almost certainly a vacancy link sent to
        # the wrong step (e.g. the previous message was mistakenly accepted
        # as "the vacancy" - see the matching check in _handle_vacancy_step),
        # not a resume. Short-message threshold only, so a real resume that
        # happens to mention a link somewhere in a lot of other text isn't
        # blocked.
        if len(text) < _MIN_COMBINED_PART_LEN and _HH_LINK_SPAN_RE.search(text):
            await message.reply_text(
                "Это похоже на ссылку на вакансию, а не на резюме. Если вакансия уже была принята "
                f"неправильно (например, резюме кандидата случайно приняли за неё) — начните заново: /start.\n\n{_ASK_FOR_RESUME}"
            )
            return
        pending["resume_text"] = text
    else:
        await message.reply_text(_ASK_FOR_RESUME)
        return

    await message.reply_text("Принял резюме, обрабатываю...")
    await _finalize_resume_and_screen(message, context, pending)


async def _finalize_resume_and_screen(message, context: ContextTypes.DEFAULT_TYPE, pending: dict) -> None:
    try:
        await _run_screening_and_reply(message, pending)
    except ResumeExtractionError as exc:
        logger.warning("resume extraction failed: %s", exc)
        await message.reply_text(f"Не удалось прочитать резюме: {exc}\n\n{_ASK_FOR_RESUME}")
        return  # keep the accepted vacancy pending, let them retry the resume only
    except ScreeningIncompleteError as exc:
        # Never show a card that might be silently missing a real flag - see
        # the exception's own docstring in screening.py (D-24).
        logger.error("screening incomplete: %s", exc)
        await message.reply_text(
            "ИИ-гейтвей вернул неполный ответ несколько раз подряд — карточку не показываю, "
            "чтобы не скрыть возможный red flag. Попробуйте отправить то же резюме ещё раз."
        )
        return  # keep the accepted vacancy pending, let them retry the resume only
    except Exception:  # noqa: BLE001 - top-level handler boundary, must not crash the bot
        logger.exception("unexpected error during screening")
        await message.reply_text("Внутренняя ошибка при обработке. Попробуйте ещё раз с /start.")
    _reset_pending(context)


async def _run_screening_and_reply(message, pending: dict) -> None:
    vacancy: VacancyInfo = pending["vacancy"]

    file_bytes, file_name = (None, None)
    if pending["resume_file"] is not None:
        file_bytes, file_name = pending["resume_file"]
    resume_text = extract_resume_text(
        file_bytes=file_bytes, file_name=file_name, plain_text=pending["resume_text"]
    )

    if LOCAL_DEBUG_LOGGING:
        logger.info("screening started (vacancy_title=%r, resume_chars=%d)", vacancy.title, len(resume_text))
    else:
        logger.info("screening started")

    pre_findings = run_all_deterministic_checks(resume_text)
    # screen_candidate uses the sync Anthropic SDK client - offload to a thread
    # so it doesn't block the bot's asyncio event loop for other chats.
    card = await asyncio.to_thread(
        screen_candidate, vacancy=vacancy, resume_text=resume_text, pre_findings=pre_findings
    )

    await message.reply_text(render_card(card), parse_mode="Markdown")

    if LOCAL_DEBUG_LOGGING:
        logger.info("screening finished (verdict=%s)", card.verdict)
    else:
        logger.info("screening finished")

    # resume_text / vacancy / pre_findings / card all go out of scope here and
    # are not persisted anywhere (no DB write, no file write, no queue) - this
    # is the whole "no storage, not even temporary" requirement, enforced by
    # simply never writing them anywhere rather than writing-then-deleting.


def build_application() -> Application:
    require_config()
    builder = Application.builder().token(TELEGRAM_BOT_TOKEN)
    if PROXY_URL:
        # Telegram's Bot API is unreliable/blocked from some Russian server
        # IPs - route both regular requests and long-polling through the
        # same proxy. Needs httpx[socks] installed if PROXY_URL is socks5://.
        builder = builder.proxy(PROXY_URL).get_updates_proxy(PROXY_URL)
    application = builder.build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT | filters.Document.ALL, handle_message))
    return application
