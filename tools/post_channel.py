#!/usr/bin/env python3
"""Günün sözünü kanala bir dəfə göndərir."""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from telegram import Bot

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

import bot as bot_module  # noqa: E402


async def main() -> None:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("BOT_TOKEN tapılmadı.")
    async with Bot(token) as telegram_bot:
        await telegram_bot.send_message(
            chat_id=bot_module.CHANNEL,
            text=bot_module.daily_text(),
        )
    print("göndərildi")


if __name__ == "__main__":
    asyncio.run(main())
