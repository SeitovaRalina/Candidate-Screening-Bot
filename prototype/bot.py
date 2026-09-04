"""Telegram bot handlers.

Per-chat pending state only pairs one candidate's vacancy+resume together
across two messages - it is cleared immediately after a card is produced.
This is NOT cross-candidate memory (see .assistant/open-questions.md OQ-3):
nothing about candidate N is available when screening candidate N+1.
"""
from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, CommandHandler, filters

from config import TELEGRAM_BOT_TOKEN, require_config
from deterministic_checks import run_all_deterministic_checks
from resume_extract import ResumeExtractionError, extract_resume_text
from screening import screen_candidate
from card import render_card
from vacancy import VacancyFetchError, fetch_vacancy

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("candidate_screening_bot")

_EMPTY_PENDING = {"vacancy": None, "resume_text": None, "resume_file": None}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Привет! Пришлите вакансию (ссылку на hh.ru или текст), затем резюме кандидата "
        "(файлом PDF/DOCX/TXT или текстом) - в любом порядке. Соберу карточку кандидата."
    )


def _reset_pending(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.chat_data["pending"] = dict(_EMPTY_PENDING)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    pending = context.chat_data.setdefault("pending", dict(_EMPTY_PENDING))

    if message.document:
        tg_file = await message.document.get_file()
        data = await tg_file.download_as_bytearray()
        pending["resume_file"] = (bytes(data), message.document.file_name)
    elif message.text:
        text = message.text.strip()
        if pending["vacancy"] is None:
            pending["vacancy"] = text
        elif pending["resume_file"] is None and pending["resume_text"] is None:
            pending["resume_text"] = text
        else:
            await message.reply_text("Уже обрабатываю пару вакансия+резюме, подождите результат.")
            return
    else:
        await message.reply_text("Пришлите текст (вакансия/резюме) или файл резюме (PDF/DOCX/TXT).")
        return

    have_resume = pending["resume_file"] is not None or pending["resume_text"] is not None
    if pending["vacancy"] and have_resume:
        await message.reply_text("Принял вакансию и резюме, обрабатываю...")
        try:
            await _run_screening_and_reply(message, pending)
        except VacancyFetchError as exc:
            logger.warning("vacancy fetch failed: %s", exc)
            await message.reply_text(f"Не удалось получить вакансию: {exc}")
        except ResumeExtractionError as exc:
            logger.warning("resume extraction failed: %s", exc)
            await message.reply_text(f"Не удалось прочитать резюме: {exc}")
        except Exception:  # noqa: BLE001 - top-level handler boundary, must not crash the bot
            logger.exception("unexpected error during screening")
            await message.reply_text("Внутренняя ошибка при обработке. Попробуйте ещё раз.")
        finally:
            _reset_pending(context)
    else:
        missing = "резюме (файл или текст)" if pending["vacancy"] else "вакансию (ссылка hh.ru или текст)"
        await message.reply_text(f"Принял. Жду ещё: {missing}.")


async def _run_screening_and_reply(message, pending: dict) -> None:
    vacancy = await fetch_vacancy(pending["vacancy"])

    file_bytes, file_name = (None, None)
    if pending["resume_file"] is not None:
        file_bytes, file_name = pending["resume_file"]
    resume_text = extract_resume_text(
        file_bytes=file_bytes, file_name=file_name, plain_text=pending["resume_text"]
    )

    logger.info("screening started (vacancy_title=%r, resume_chars=%d)", vacancy.title, len(resume_text))

    pre_findings = run_all_deterministic_checks(resume_text)
    # screen_candidate uses the sync Anthropic SDK client - offload to a thread
    # so it doesn't block the bot's asyncio event loop for other chats.
    card = await asyncio.to_thread(
        screen_candidate, vacancy=vacancy, resume_text=resume_text, pre_findings=pre_findings
    )

    await message.reply_text(render_card(card), parse_mode="Markdown")
    logger.info("screening finished (verdict=%s)", card.verdict)


def build_application() -> Application:
    require_config()
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT | filters.Document.ALL, handle_message))
    return application
