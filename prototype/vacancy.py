"""Vacancy ingestion: hh.ru public vacancy page for links, plain text otherwise.

Why the public HTML page and not api.hh.ru: verified live 2026-09-04 that
api.hh.ru/vacancies closed unauthorized access in April 2026 (403 on every
request regardless of User-Agent — see D-9). The plain vacancy webpage
(https://hh.ru/vacancy/{id}) has no such gate — it returns 200 with no login,
and robots.txt disallows /auth, /login, /account, /resume, but NOT /vacancy —
this is public marketing content, not gated data. The page embeds a
schema.org JobPosting JSON-LD block (put there for search-engine indexing,
i.e. explicitly meant to be machine-read), which is used here instead of
regex-scraping the HTML layout.

This is a different thing from the personal-account login path this project
explicitly excludes (see anti-stories.md, OQ-5's login-specific half): no
credentials, no session, no account — just a GET on a page hh.ru serves to
anyone. It does not help with hidden/direct vacancies (those genuinely need
an authenticated session or a registered API app), only with public ones.
"""
from __future__ import annotations

import html
import json
import re

import httpx

from models import VacancyInfo

_HH_URL_RE = re.compile(r"hh\.ru/vacancy/(\d+)", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_JSON_LD_RE = re.compile(
    r'<script type="application/ld\+json">\s*(\{.*?"@type"\s*:\s*"JobPosting".*?\})\s*</script>',
    re.DOTALL,
)

_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


class VacancyFetchError(RuntimeError):
    """Raised when a hh.ru link is given but the vacancy can't be resolved.

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
        return await _fetch_from_public_page(match.group(1), source_url=text.strip())
    return VacancyInfo(title="(из текста, без ссылки)", description=text.strip())


async def _fetch_from_public_page(vacancy_id: str, *, source_url: str) -> VacancyInfo:
    url = f"https://hh.ru/vacancy/{vacancy_id}"
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(url, headers={"User-Agent": _BROWSER_USER_AGENT})

    if resp.status_code == 404:
        raise VacancyFetchError(
            f"hh.ru vacancy {vacancy_id} not found (404) — expired, private, or the link is wrong."
        )
    resp.raise_for_status()
    resp.encoding = "utf-8"

    match = _JSON_LD_RE.search(resp.text)
    if not match:
        # Most likely a hidden/direct vacancy or an anti-bot interstitial
        # rather than a plain public posting - out of MVP scope either way.
        raise VacancyFetchError(
            "Не нашла структурированные данные вакансии на странице hh.ru — возможно, это "
            "скрытая/прямая вакансия (не входит в MVP) или hh.ru показал антибот-страницу. "
            "Пришлите текст вакансии напрямую."
        )

    data = json.loads(match.group(1))
    org = (data.get("hiringOrganization") or {}).get("name")
    title = data.get("title") or "(без названия)"
    if org:
        title = f"{title} — {org}"

    return VacancyInfo(
        title=title,
        description=_strip_html(data.get("description") or ""),
        key_skills=[],  # not present in hh.ru's JobPosting JSON-LD; LLM step reads requirements from description text
        experience=None,
        source_url=source_url,
    )
