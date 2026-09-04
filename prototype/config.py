"""Environment configuration. Secrets come from env vars only — never hard-code
a token/key here or pass one through a prompt (see .memory-bank/steerings/project-rules.md).
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

# Telegram's Bot API can be unreachable from some Russian server IPs. If set,
# used explicitly for python-telegram-bot's requests (bot.py); httpx (used by
# both this and the anthropic SDK) also auto-picks up the standard
# HTTPS_PROXY/HTTP_PROXY env vars on its own for vacancy.py/screening.py's
# calls, so setting those two is usually enough on its own - PROXY_URL only
# matters for python-telegram-bot specifically wiring the same proxy in.
PROXY_URL = os.environ.get("PROXY_URL", "")

# Routed through Effective's internal LiteLLM gateway (llm.effective.land), not
# api.anthropic.com directly - ANTHROPIC_API_KEY holds the gateway's virtual key
# (issued by whoever admins the gateway), not a raw Anthropic key. Empty
# LITELLM_BASE_URL falls back to calling Anthropic directly, for local testing
# with a personal key if the gateway is ever unreachable.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
LITELLM_BASE_URL = os.environ.get("LITELLM_BASE_URL", "https://llm.effective.land")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")

# Client requirement (2026-09-04, reply to communications/2026-09-04-kickoff-followup.md
# item 4): zero resume storage anywhere in production, "even temporary" -
# extends to logs, not just a database. Default OFF (production posture);
# turn on only on your own machine for local debugging, never in a deployed
# instance. When off, logs carry counts/verdicts only, never vacancy titles
# or anything that could roundtrip to a specific candidate/resume.
LOCAL_DEBUG_LOGGING = os.environ.get("LOCAL_DEBUG_LOGGING", "false").strip().lower() == "true"

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
