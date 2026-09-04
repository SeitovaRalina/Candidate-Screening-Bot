"""Vacancy fetch tests use httpx.MockTransport - no real network call.

Source is hh.ru's public vacancy webpage (JSON-LD JobPosting embed), not
api.hh.ru - see vacancy.py module docstring for why (D-9: api.hh.ru closed
unauthorized access in April 2026; the public page has no such gate).
"""
import httpx
import pytest

import vacancy

_RealAsyncClient = httpx.AsyncClient


def _patch_client(monkeypatch, handler):
    def fake_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return _RealAsyncClient(*args, **kwargs)

    monkeypatch.setattr(vacancy.httpx, "AsyncClient", fake_client)


def _page_with_job_posting(title: str, description_html: str, org: str) -> str:
    return f"""<!DOCTYPE html><html><head>
<script type="application/ld+json">
{{"@context":"https://schema.org/","@type":"JobPosting","title":"{title}",
"description":"{description_html}","hiringOrganization":{{"@type":"Organization","name":"{org}"}}}}
</script>
</head><body>irrelevant page chrome</body></html>"""


@pytest.mark.asyncio
async def test_plain_text_without_link_is_used_as_is():
    info = await vacancy.fetch_vacancy("Ищем Python-разработчика, опыт от 3 лет")
    assert info.title == "(из текста, без ссылки)"
    assert "Python" in info.description


@pytest.mark.asyncio
async def test_hh_link_404_raises_clear_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    _patch_client(monkeypatch, handler)

    with pytest.raises(vacancy.VacancyFetchError, match="not found"):
        await vacancy.fetch_vacancy("https://hh.ru/vacancy/12345678")


@pytest.mark.asyncio
async def test_hh_link_without_job_posting_raises_clear_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html><body>no structured data here</body></html>")

    _patch_client(monkeypatch, handler)

    with pytest.raises(vacancy.VacancyFetchError, match="структурированные данные"):
        await vacancy.fetch_vacancy("https://hh.ru/vacancy/12345678")


@pytest.mark.asyncio
async def test_hh_link_success_parses_job_posting(monkeypatch):
    page = _page_with_job_posting(
        title="Python Developer",
        description_html="<p>Нужен <b>Python</b></p>",
        org="Acme",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=page)

    _patch_client(monkeypatch, handler)

    info = await vacancy.fetch_vacancy("https://hh.ru/vacancy/12345678")
    assert info.title == "Python Developer — Acme"
    assert "<b>" not in info.description
    assert "Python" in info.description
