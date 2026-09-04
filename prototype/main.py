"""Entrypoint: python main.py"""
from __future__ import annotations

import asyncio

from bot import build_application


def main() -> None:
    # python-telegram-bot 21.7's run_polling() calls asyncio.get_event_loop()
    # internally, relying on it implicitly creating a loop when none exists
    # in the main thread - Python 3.14 removed that implicit creation
    # (RuntimeError: "There is no current event loop"). Set one explicitly
    # instead of bumping library versions under time pressure.
    asyncio.set_event_loop(asyncio.new_event_loop())
    application = build_application()
    application.run_polling()


if __name__ == "__main__":
    main()
