"""Render a CandidateCard as a Telegram message (MarkdownV2-safe plain formatting
kept simple on purpose - a prototype has no reason to fight Telegram's markdown
escaping rules; plain text with emoji separators is legible and robust).
"""
from __future__ import annotations

from models import CandidateCard, Flag

_VERDICT_LABELS = {
    "fit": "✅ Подходит — можно звать на тех. интервью",
    "not_fit": "❌ Не подходит",
    "unclear": "⚠️ Неоднозначно — нужна ручная проверка",
}


def _format_flag(flag: Flag, bullet: str) -> str:
    # Not "[code]" - square brackets collide with Telegram Markdown's inline
    # link syntax ([text](url)) and get silently stripped mid-sentence,
    # found live testing case 2 ("...2021 - 2024 code" with no brackets at
    # all in the rendered message).
    marker = " 🔧" if flag.source == "deterministic" else ""
    return f"{bullet} {flag.text}{marker}\n   > «{flag.quote}»"


def render_card(card: CandidateCard) -> str:
    lines: list[str] = []
    lines.append(_VERDICT_LABELS.get(card.verdict, card.verdict))
    lines.append("")
    lines.append("*Green flags:*" if card.green_flags else "*Green flags:* нет")
    for flag in card.green_flags:
        lines.append(_format_flag(flag, "🟢"))
    lines.append("")
    lines.append("*Red flags:*" if card.red_flags else "*Red flags:* нет")
    for flag in card.red_flags:
        lines.append(_format_flag(flag, "🔴"))
    lines.append("")
    lines.append("*Вопросы для тех. интервью:*")
    for i, question in enumerate(card.interview_questions, start=1):
        lines.append(f"{i}. {question}")
    lines.append("")
    lines.append("_Это рекомендация. Финальное решение — за вами._")
    return "\n".join(lines)
