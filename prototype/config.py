"""Environment configuration. Secrets come from env vars only — never hard-code
a token/key here or pass one through a prompt (see .memory-bank/steerings/project-rules.md).
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")

# How long to hold a candidate's vacancy/resume in memory while waiting for the
# second half of the pair (in seconds). This is per-submission pairing state
# only, cleared right after a card is produced — not the same thing as
# cross-candidate memory. See .assistant/open-questions.md OQ-3 (bot must not
# retain/reuse data from a previous candidate when screening the next one).
PENDING_PAIR_TTL_SECONDS = int(os.environ.get("PENDING_PAIR_TTL_SECONDS", "600"))


def require_config() -> None:
    missing = [
        name
        for name, value in (
            ("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN),
            ("ANTHROPIC_API_KEY", ANTHROPIC_API_KEY),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            "Copy .env.example to .env and fill them in."
        )
