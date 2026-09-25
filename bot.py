#!/usr/bin/env python3
"""Azərbaycan atalar sözləri maarifləndirmə botu."""

from __future__ import annotations

import json
import logging
import os
import random
import re
from pathlib import Path

from dotenv import load_dotenv
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

load_dotenv()

LOGGING_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
logging.basicConfig(format=LOGGING_FORMAT, level=logging.INFO)
logger = logging.getLogger("atalar")

ACAR, HEKAYE = range(2)

DATA_PATH = Path(__file__).with_name("proverbs.json")


def load_proverbs() -> list[dict]:
    with DATA_PATH.open(encoding="utf-8") as f:
        data = json.load(f)
    return data["proverbs"]


PROVERBS = load_proverbs()

MENU_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["🔑 Açar söz", "📖 Hekayə"],
        ["🎲 Təsadüfi", "ℹ️ Kömək"],
    ],
    resize_keyboard=True,
)


def normalize(text: str) -> str:
    text = text.lower().strip()
    replacements = {
        "ə": "e",
        "ı": "i",
        "ö": "o",
        "ü": "u",
        "ğ": "g",
        "ş": "s",
        "ç": "c",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokens(text: str) -> set[str]:
    return {t for t in normalize(text).split() if len(t) > 1}


def format_proverb(item: dict, sira: int | None = None) -> str:
    bashliq = f"{sira}. " if sira is not None else ""
    return (
        f"{bashliq}«{item['text']}»\n"
        f"Məna: {item['mena']}\n"
        f"Mövzu: {', '.join(item['movzu'])}"
    )


def search_by_keyword(query: str, limit: int = 8) -> list[tuple[int, dict]]:
    q_norm = normalize(query)
    q_tokens = tokens(query)
    if not q_norm:
        return []

    scored: list[tuple[int, dict]] = []
    for item in PROVERBS:
        haystack = " ".join(
            [item["text"], item["mena"], " ".join(item["acar"]), " ".join(item["movzu"])]
        )
        hay_norm = normalize(haystack)
        hay_tokens = tokens(haystack)
        score = 0
        if q_norm in hay_norm:
            score += 8
        overlap = q_tokens & hay_tokens
        score += 3 * len(overlap)
        for word in q_tokens:
            if any(word in t or t in word for t in hay_tokens if len(word) >= 3):
                score += 1
        if score > 0:
            scored.append((score, item))

    scored.sort(key=lambda x: (-x[0], x[1]["id"]))
    return scored[:limit]


def search_by_story(story: str, limit: int = 5) -> list[tuple[int, dict]]:
    """Hekayəni açar söz və mövzu kəsişməsinə görə qiymətləndirir."""
    return search_by_keyword(story, limit=limit)


def main_menu_text() -> str:
    return (
        "Salam. Bu bot yalnız Azərbaycan atalar sözlərini öyrədir.\n\n"
        f"Bazada indi {len(PROVERBS)} atalar sözü var.\n\n"
        "Nə etmək istəyirsən?\n"
        "• Açar söz — bir söz yaz, uyğun atalar sözünü tapım.\n"
        "• Hekayə — vəziyyəti danış, uyğun atalar sözünü deyim.\n"
        "• Təsadüfi — təsadüfi bir atalar sözü oxu."
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(main_menu_text(), reply_markup=MENU_KEYBOARD)
    return ConversationHandler.END


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (
        "Əmrlər:\n"
        "/start — əsas menyu\n"
        "/acar — açar sözlə axtarış\n"
        "/hekaye — hekayəyə uyğun atalar sözü\n"
        "/tesaduf — təsadüfi atalar sözü\n"
        "/legv — axtarışı dayandır\n\n"
        "Nümunə açar söz: dost, zəhmət, vaxt, elm, ana\n"
        "Nümunə hekayə: İşimi sabaha saxladım, sonra peşman oldum."
    )
    await update.message.reply_text(text, reply_markup=MENU_KEYBOARD)
    return ConversationHandler.END


async def random_proverb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    item = random.choice(PROVERBS)
    await update.message.reply_text(
        "Təsadüfi atalar sözü:\n\n" + format_proverb(item),
        reply_markup=MENU_KEYBOARD,
    )
    return ConversationHandler.END


async def ask_keyword(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Açar sözü yaz. Məsələn: dost, zəhmət, elm, vaxt.\n"
        "Ləğv etmək üçün /legv yaz.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ACAR


async def ask_story(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Vəziyyəti və ya qısa hekayəni yaz.\n"
        "Məsələn: Dostum çətin gündə yanımdan getdi.\n"
        "Ləğv etmək üçün /legv yaz.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return HEKAYE


def result_text(title: str, results: list[tuple[int, dict]], empty_hint: str) -> str:
    if not results:
        return empty_hint
    lines = [title, ""]
    for i, (_score, item) in enumerate(results, start=1):
        lines.append(format_proverb(item, sira=i))
        lines.append("")
    return "\n".join(lines).strip()


async def route_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    text = (update.message.text or "").strip()
    if text in {"🔑 Açar söz", "Açar söz"}:
        return await ask_keyword(update, context)
    if text in {"📖 Hekayə", "Hekayə"}:
        return await ask_story(update, context)
    if text in {"🎲 Təsadüfi", "Təsadüfi"}:
        return await random_proverb(update, context)
    if text in {"ℹ️ Kömək", "Kömək"}:
        return await help_cmd(update, context)
    return None


async def handle_keyword(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    routed = await route_menu(update, context)
    if routed is not None:
        return routed
    query = (update.message.text or "").strip()
    results = search_by_keyword(query)
    text = result_text(
        f"«{query}» üçün tapılan atalar sözləri:",
        results,
        "Bu açar sözə uyğun atalar sözü tapılmadı. Başqa söz yoxla və ya bazanı genişləndir.",
    )
    await update.message.reply_text(text, reply_markup=MENU_KEYBOARD)
    return ConversationHandler.END


async def handle_story(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    routed = await route_menu(update, context)
    if routed is not None:
        return routed
    story = (update.message.text or "").strip()
    results = search_by_story(story)
    text = result_text(
        "Hekayənə uyğun atalar sözləri:",
        results,
        "Bu hekayəyə yaxın atalar sözü tapılmadı. Bir az daha konkret yaz: kim, nə oldu, nə hiss etdin.",
    )
    await update.message.reply_text(text, reply_markup=MENU_KEYBOARD)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Axtarış dayandırıldı.", reply_markup=MENU_KEYBOARD)
    return ConversationHandler.END


async def menu_text_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    routed = await route_menu(update, context)
    if routed is not None:
        return routed
    await update.message.reply_text(
        "Menyudan seç və ya /acar, /hekaye yaz.",
        reply_markup=MENU_KEYBOARD,
    )
    return ConversationHandler.END


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Xəta: %s", context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "Bir xəta oldu. Bir az sonra yenə yoxla."
        )


def build_app(token: str) -> Application:
    request = HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0,
    )
    updates = HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=40.0,
        write_timeout=30.0,
        pool_timeout=30.0,
    )
    app = (
        Application.builder()
        .token(token)
        .request(request)
        .get_updates_request(updates)
        .build()
    )

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("acar", ask_keyword),
            CommandHandler("hekaye", ask_story),
            MessageHandler(filters.Regex(r"^(🔑 Açar söz|Açar söz)$"), ask_keyword),
            MessageHandler(filters.Regex(r"^(📖 Hekayə|Hekayə)$"), ask_story),
        ],
        states={
            ACAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_keyword)],
            HEKAYE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_story)],
        },
        fallbacks=[
            CommandHandler("legv", cancel),
            CommandHandler("start", start),
            CommandHandler("komek", help_cmd),
            CommandHandler("help", help_cmd),
            CommandHandler("tesaduf", random_proverb),
        ],
        allow_reentry=True,
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("komek", help_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("tesaduf", random_proverb))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_text_router))
    app.add_error_handler(on_error)
    return app


def main() -> None:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token or token.startswith("1234567890"):
        raise SystemExit(
            "BOT_TOKEN tapılmadı. .env.example-i .env kimi kopyala və tokeni yaz."
        )
    logger.info("Bot başladı. Atalar sözü sayı: %s", len(PROVERBS))
    application = build_app(token)
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        bootstrap_retries=-1,
        timeout=20,
    )


if __name__ == "__main__":
    main()
