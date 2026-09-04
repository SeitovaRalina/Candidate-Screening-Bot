"""Vacancy fetch tests use httpx.MockTransport - no real network call, and no
dependency on hh.ru's actual (currently broken, see OQ-5/D-9) API access.
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


@pytest.mark.asyncio
async def test_plain_text_without_link_is_used_as_is():
    info = await vacancy.fetch_vacancy("Ищем Python-разработчика, опыт от 3 лет")
    assert info.title == "(из текста, без ссылки)"
    assert "Python" in info.description


@pytest.mark.asyncio
async def test_hh_link_403_raises_clear_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"errors": [{"type": "forbidden"}]})

    _patch_client(monkeypatch, handler)

    with pytest.raises(vacancy.VacancyFetchError, match="403"):
        await vacancy.fetch_vacancy("https://hh.ru/vacancy/12345678")


@pytest.mark.asyncio
async def test_hh_link_success_parses_fields(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "name": "Python Developer",
                "description": "<p>Нужен <b>Python</b></p>",
                "key_skills": [{"name": "Python"}, {"name": "SQL"}],
                "experience": {"name": "От 3 до 6 лет"},
            },
        )

    _patch_client(monkeypatch, handler)

    info = await vacancy.fetch_vacancy("https://hh.ru/vacancy/12345678")
    assert info.title == "Python Developer"
    assert info.key_skills == ["Python", "SQL"]
    assert info.experience == "От 3 до 6 лет"
    assert "<b>" not in info.description
