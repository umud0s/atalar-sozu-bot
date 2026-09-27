#!/usr/bin/env python3
"""Kanala bir dəfəlik qarşılama yazısı göndərir və onu sabitləyir."""

import asyncio
import os

from dotenv import load_dotenv
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

load_dotenv()

CHANNEL = "@atalarimizinsozu"
BOT_LINK = "https://t.me/AtalarSozleri_bot"

WELCOME = (
    "Salam.\n\n"
    "Bu kanal Azərbaycan atalar sözü üçündür.\n"
    "Hər səhər saat 09:00-da bir söz dərc olunur.\n\n"
    "Sözü axtarmaq, mövzu seçmək, günün sözünü oxumaq "
    "və quiz oynamaq üçün bota keçin."
)

DESCRIPTION = (
    "Hər səhər saat 09:00-da bir Azərbaycan atalar sözü. "
    "Axtarış, mövzu və quiz üçün bot: @AtalarSozleri_bot"
)


async def main() -> None:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token or token.startswith("1234567890"):
        raise SystemExit("BOT_TOKEN tapılmadı.")
    bot = Bot(token)
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Bota keç", url=BOT_LINK)]]
    )
    async with bot:
        message = await bot.send_message(
            chat_id=CHANNEL,
            text=WELCOME,
            reply_markup=keyboard,
        )
        await bot.pin_chat_message(
            chat_id=CHANNEL,
            message_id=message.message_id,
        )
        await bot.set_chat_description(
            chat_id=CHANNEL,
            description=DESCRIPTION,
        )
    print("Qarşılama göndərildi və sabitləndi.")


if __name__ == "__main__":
    asyncio.run(main())
