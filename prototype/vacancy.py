"""Vacancy ingestion: hh.ru public API for links, plain text otherwise.

MVP scope only covers public hh.ru vacancies via the official API — no login,
no scraping. See .memory-bank/product-overview/anti-stories.md: hidden/direct
vacancies behind a personal hh.ru account are explicitly out of scope pending
client approval + guardrail review (OQ-5).
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass

import httpx

from models import VacancyInfo

_HH_URL_RE = re.compile(r"hh\.ru/vacancy/(\d+)", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


class VacancyFetchError(RuntimeError):
    """Raised when a hh.ru link is given but the vacancy can't be fetched.

    Deliberately not swallowed into "treat as plain text" — a broken/expired
    link silently downgrading to garbage input would produce a screening card
    the recruiter can't trust, which violates the evidence-required rule in
    project-rules.md.
    """


def _strip_html(raw: str) -> str:
    unescaped = html.unescape(raw)
    return _TAG_RE.sub(" ", unescaped).strip()


async def fetch_vacancy(text: str) -> VacancyInfo:
    """Resolve a vacancy from either an hh.ru link or raw pasted text."""
    match = _HH_URL_RE.search(text)
    if match:
        return await _fetch_from_hh_api(match.group(1), source_url=text.strip())
    return VacancyInfo(title="(из текста, без ссылки)", description=text.strip())


async def _fetch_from_hh_api(vacancy_id: str, *, source_url: str) -> VacancyInfo:
    url = f"https://api.hh.ru/vacancies/{vacancy_id}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, headers={"User-Agent": "candidate-screening-bot/0.1 (prototype)"})
    if resp.status_code == 404:
        raise VacancyFetchError(
            f"hh.ru vacancy {vacancy_id} not found (404) — expired, private, or the link is wrong."
        )
    if resp.status_code == 403:
        # Verified 2026-09-04: hh.ru closed unauthorized access to /vacancies
        # (even single-vacancy GET) as of April 2026 - this is not a bug in
        # this code, the public no-login API this MVP was scoped around no
        # longer exists. See .assistant/open-questions.md OQ-5 (upgraded to
        # blocking) and .assistant/decisions.md D-9. Until Anton confirms a
        # registered hh.ru API app (client_id/secret via employer account),
        # paste the vacancy text directly instead of a link.
        raise VacancyFetchError(
            "hh.ru API вернул 403 — публичный доступ без авторизованного приложения сейчас закрыт "
            "(это ограничение hh.ru, не баг бота). Пока пришлите текст вакансии напрямую, "
            "не ссылку — см. OQ-5."
        )
    resp.raise_for_status()
    data = resp.json()

    description = _strip_html(data.get("description") or "")
    key_skills = [s["name"] for s in data.get("key_skills", []) if s.get("name")]
    experience = (data.get("experience") or {}).get("name")

    return VacancyInfo(
        title=data.get("name", "(без названия)"),
        description=description,
        key_skills=key_skills,
        experience=experience,
        source_url=source_url,
    )
