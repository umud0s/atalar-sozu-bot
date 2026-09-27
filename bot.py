#!/usr/bin/env python3
"""Azərbaycan atalar sözləri maarifləndirmə botu."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InputTextMessageContent,
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
    InlineQueryHandler,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

load_dotenv()

LOGGING_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
logging.basicConfig(format=LOGGING_FORMAT, level=logging.INFO)
logger = logging.getLogger("atalar")

ACAR, HEKAYE, QUIZ = range(3)

DATA_PATH = Path(__file__).with_name("proverbs.json")
STATS_PATH = Path(__file__).with_name("quiz_stats.json")
_stats_lock = asyncio.Lock()


def load_proverbs() -> list[dict]:
    with DATA_PATH.open(encoding="utf-8") as f:
        data = json.load(f)
    return data["proverbs"]


PROVERBS = load_proverbs()
CHANNEL = "@atalarimizinsozu"
BAKI = timezone(timedelta(hours=4))

MENU_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["🔑 Açar söz", "📖 Hekayə"],
        ["🎲 Təsadüfi", "📚 Mövzular"],
        ["🌅 Günün sözü", "🧩 Quiz"],
        ["ℹ️ Kömək"],
    ],
    resize_keyboard=True,
)
QUIZ_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["⏭ Pas"],
        ["🔑 Açar söz", "📖 Hekayə"],
        ["🎲 Təsadüfi", "📚 Mövzular"],
        ["🌅 Günün sözü", "🧩 Quiz"],
        ["ℹ️ Kömək"],
    ],
    resize_keyboard=True,
)

TOPICS = [
    "Əxlaq",
    "Nəsihət",
    "Tərbiyə",
    "Təhsil",
    "Ağıl",
    "Dostluq",
    "Ailə",
    "İş",
    "Ortaqlıq",
    "Bərəkət",
    "Adət-ənənə",
    "El",
]


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
    stop = {
        "bir", "bu", "da", "de", "ve", "ile", "ucun", "sonra", "amma",
        "men", "sen", "ki", "cox", "olan", "olsun", "hec", "artiq", "indi",
        "ona", "bunu", "bele", "ele", "nece", "cunki", "lakin", "hem",
        "qeder", "mene", "sene", "oz", "ozum", "idi", "imish",
    }
    return {t for t in normalize(text).split() if len(t) > 1 and t not in stop}


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
        if len(q_norm) <= 3:
            if q_norm in hay_tokens:
                score += 8
        elif q_norm in hay_norm:
            score += 8
        overlap = q_tokens & hay_tokens
        score += 3 * len(overlap)
        for word in q_tokens:
            if len(word) < 4:
                continue
            if any(word in t or t in word for t in hay_tokens):
                score += 1
        if score > 0:
            scored.append((score, item))

    scored.sort(key=lambda x: (-x[0], x[1]["id"]))
    return scored[:limit]


def _triggered(words: set[str], triggers: set[str]) -> bool:
    for word in words:
        for trigger in triggers:
            if word == trigger:
                return True
            if len(trigger) >= 4 and (word.startswith(trigger) or trigger.startswith(word)):
                return True
    return False


def search_by_story(story: str, limit: int = 3) -> list[tuple[int, dict]]:
    """Hekayədəki vəziyyəti mövzulara bağlayıb ən yaxın sözləri seçir."""
    q_tokens = tokens(story)
    if not q_tokens:
        return []

    situations = [
        ({"sabah", "saxladim", "tehir", "gecikdim", "gecikdi"}, {"sabah", "vaxt"}),
        ({"dost", "dostum", "yoldas", "terk", "buraxdi", "satdi"}, {"dost", "sadiq", "dar"}),
        ({"qonsu", "qonsum", "dalasdiq"}, {"qonsu", "qonsuluq"}),
        ({"yalan", "aldadi", "aldandim", "inanmadi"}, {"yalan", "etibar", "heqiqet"}),
        ({"borc", "pul", "xercl", "xercler"}, {"borc", "qenaet", "pul"}),
        ({"ana", "anam", "ata", "atam", "usaq", "ovlad"}, {"ana", "ata", "terbiye", "aile"}),
        ({"qorxdum", "qorxu"}, {"qorxu", "igid"}),
        ({"tek", "komek", "yanliz"}, {"birlik", "komek", "paylas"}),
        ({"tembel", "islemedim", "zehmet"}, {"is", "zehmet", "emek"}),
        ({"qezeb", "aciqlandim", "hirs"}, {"soz", "sus", "ehtiyat"}),
        ({"sir", "sirri"}, {"sir", "soz"}),
        ({"veten", "qurbet"}, {"veten", "el", "deyer"}),
        ({"elm", "oxudum", "mekteb", "muellim"}, {"elm", "oyren"}),
        ({"kusdum", "baris", "bagisla"}, {"baris", "bagis"}),
        ({"xesis", "paylasmadim"}, {"paylas", "qenaet"}),
    ]
    wanted: set[str] = set()
    for triggers, targets in situations:
        if _triggered(q_tokens, triggers):
            wanted |= targets

    scored: list[tuple[int, dict]] = []
    for score, item in search_by_keyword(story, limit=len(PROVERBS)):
        hay = tokens(" ".join([item["text"], item["mena"], " ".join(item["acar"]), " ".join(item["movzu"])]))
        extra = 4 * len(wanted & hay)
        total = score + extra
        if total >= 4:
            scored.append((total, item))
    scored.sort(key=lambda x: (-x[0], x[1]["id"]))
    return scored[:limit]


def main_menu_text() -> str:
    return (
        "Salam. Bu bot yalnız Azərbaycan atalar sözlərini öyrədir.\n\n"
        f"Bazada indi {len(PROVERBS)} atalar sözü var.\n\n"
        "Nə etmək istəyirsən?\n"
        "• Açar söz — bir söz yaz, uyğun atalar sözünü tapım.\n"
        "• Hekayə — vəziyyəti danış, uyğun atalar sözünü deyim.\n"
        "• Təsadüfi — təsadüfi bir atalar sözü oxu.\n"
        "• Mövzular — dostluq, zəhmət, elm kimi bölmədən oxu.\n"
        "• Günün sözü — bu gün hamı üçün eyni bir atalar sözü.\n"
        "• Quiz — çatışmayan sözü tamamla. Cavabdan sonra sənin statistikən görünür."
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
        "/movzu — mövzuya görə bax\n"
        "/gun — günün atalar sözü\n"
        "/quiz — çatışmayan sözü tamamla\n"
        "/legv — axtarışı dayandır\n\n"
        "Nümunə açar söz: dost, zəhmət, vaxt, elm, ana\n"
        "Nümunə hekayə: İşimi sabaha saxladım, sonra peşman oldum.\n\n"
        "İstənilən söhbətdə @AtalarSozleri_bot yaz, arxasınca açar söz əlavə et və nəticəni ora göndər."
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


QUIZ_STOP = {
    "bir", "bu", "da", "de", "ve", "ile", "ucun", "sonra", "amma", "ki",
    "cox", "olan", "olsun", "hec", "artiq", "indi", "ona", "bunu", "bele",
    "ele", "nece", "cunki", "lakin", "hem", "qeder", "mene", "sene", "oz",
    "ozum", "idi", "imish", "olan", "gore", "kimi", "hara", "ne", "kim",
    "her", "var", "yox", "deyil", "ile", "sonra",
}
QUIZ_WORD = re.compile(r"[0-9A-Za-zƏəIıÖöÜüĞğŞşÇçİ]+")


def _quiz_word(item: dict) -> re.Match[str] | None:
    text = item["text"]
    found = list(QUIZ_WORD.finditer(text))
    acar = {normalize(word) for word in item.get("acar") or []}
    best: tuple[int, re.Match[str]] | None = None
    for index, match in enumerate(found):
        raw = match.group()
        key = normalize(raw)
        if len(key) < 3 or key in QUIZ_STOP:
            continue
        score = len(key) + index
        if key in acar or any(len(a) >= 4 and (key.startswith(a) or a.startswith(key)) for a in acar):
            score += 8
        if key.endswith(("maz", "mez")):
            score -= 7
        elif len(key) <= 9 and key.endswith(("ar", "er", "ir", "ur")):
            score -= 5
        if best is None or score > best[0]:
            best = (score, match)
    return None if best is None else best[1]


def make_quiz(item: dict) -> tuple[str, str] | None:
    match = _quiz_word(item)
    if match is None:
        return None
    hidden = match.group()
    shown = item["text"][: match.start()] + "……" + item["text"][match.end() :]
    return shown, hidden


def quiz_prompt(shown: str) -> str:
    return (
        f"«{shown}»\n\n"
        "Çatışmayan sözü tamamla.\n"
        "Bilmirsənsə, Pas düyməsinə bas."
    )


def quiz_izah(item: dict) -> str:
    if item["mena"] == "Xalq öyüdü.":
        return "Bu atalar sözünün izahı onun öz mənasındadır."
    return item["mena"]


def stat_line(row: dict) -> str:
    return f"Statistika: düzgün {row['duz']}, səhv {row['sehv']}, pas {row['pas']}"


async def add_quiz_stat(user_id: int, kind: str) -> dict:
    async with _stats_lock:
        if STATS_PATH.exists():
            try:
                data = json.loads(STATS_PATH.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data = {}
        else:
            data = {}
        row = data.get(str(user_id)) or {"duz": 0, "sehv": 0, "pas": 0}
        row[kind] = int(row.get(kind, 0)) + 1
        data[str(user_id)] = row
        temporary = STATS_PATH.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(STATS_PATH)
        return row


def clear_quiz(context: ContextTypes.DEFAULT_TYPE) -> None:
    for key in ("quiz_word", "quiz_item", "quiz_shown"):
        context.user_data.pop(key, None)


def answers_match(guess: str, expected: str) -> bool:
    got = normalize(guess)
    want = normalize(expected)
    if not got or not want:
        return False
    if got == want:
        return True
    parts = got.split()
    if len(parts) <= 3 and want in parts:
        return True
    if len(got) >= 3 and len(want) >= 3 and abs(len(got) - len(want)) <= 3:
        return got.startswith(want) or want.startswith(got)
    return False


async def ask_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    for _ in range(30):
        item = random.choice(PROVERBS)
        made = make_quiz(item)
        if made is None:
            continue
        shown, hidden = made
        context.user_data["quiz_item"] = item
        context.user_data["quiz_word"] = hidden
        context.user_data["quiz_shown"] = shown
        await update.message.reply_text(quiz_prompt(shown), reply_markup=QUIZ_KEYBOARD)
        return QUIZ
    await update.message.reply_text("Quiz hazırlanmadı. Bir az sonra yenə yoxla.", reply_markup=MENU_KEYBOARD)
    return ConversationHandler.END


async def handle_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    routed = await route_menu(update, context)
    if routed is not None:
        return routed
    guess = (update.message.text or "").strip()
    expected = context.user_data.get("quiz_word", "")
    shown = context.user_data.get("quiz_shown", "")
    item = context.user_data.get("quiz_item")
    if not expected or not item:
        return await ask_quiz(update, context)
    user_id = update.effective_user.id if update.effective_user else 0
    if answers_match(guess, expected):
        clear_quiz(context)
        row = await add_quiz_stat(user_id, "duz")
        await update.message.reply_text(
            "Düzdür. Təbrik edirəm.\n\n"
            f"«{item['text']}»\n"
            f"İzah: {quiz_izah(item)}\n\n"
            f"{stat_line(row)}",
            reply_markup=MENU_KEYBOARD,
        )
        return ConversationHandler.END
    if guess in {"⏭ Pas", "Pas", "pas"} or normalize(guess) == "pas":
        clear_quiz(context)
        row = await add_quiz_stat(user_id, "pas")
        await update.message.reply_text(
            "Pas.\n\n"
            f"Çatışmayan söz: {expected}\n"
            f"«{item['text']}»\n"
            f"İzah: {quiz_izah(item)}\n\n"
            f"{stat_line(row)}",
            reply_markup=MENU_KEYBOARD,
        )
        return ConversationHandler.END
    row = await add_quiz_stat(user_id, "sehv")
    await update.message.reply_text(
        "Səhvdir. Çatışmayan sözü bir daha yaz.\n\n"
        + quiz_prompt(shown)
        + f"\n\n{stat_line(row)}",
        reply_markup=QUIZ_KEYBOARD,
    )
    return QUIZ


async def route_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    text = (update.message.text or "").strip()
    if text in {"🔑 Açar söz", "Açar söz"}:
        return await ask_keyword(update, context)
    if text in {"📖 Hekayə", "Hekayə"}:
        return await ask_story(update, context)
    if text in {"🎲 Təsadüfi", "Təsadüfi"}:
        return await random_proverb(update, context)
    if text in {"📚 Mövzular", "Mövzular"}:
        return await show_topics(update, context)
    if text in {"🌅 Günün sözü", "Günün sözü"}:
        return await daily_proverb(update, context)
    if text in {"ℹ️ Kömək", "Kömək"}:
        return await help_cmd(update, context)
    if text in {"🧩 Quiz", "Quiz"}:
        return await ask_quiz(update, context)
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


def daily_text(day: datetime.date | None = None) -> str:
    day = day or datetime.now(BAKI).date()
    item = PROVERBS[day.toordinal() % len(PROVERBS)]
    return (
        f"Günün sözü, {day.strftime('%d.%m.%Y')}:\n\n"
        + format_proverb(item)
        + "\n\nDaha çoxu üçün: @AtalarSozleri_bot"
    )


async def daily_proverb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(daily_text(), reply_markup=MENU_KEYBOARD)
    return ConversationHandler.END


async def post_daily_to_channel(context: ContextTypes.DEFAULT_TYPE) -> None:
    day = datetime.now(BAKI).date()
    await context.bot.send_message(chat_id=CHANNEL, text=daily_text(day))
    logger.info("Kanala günün sözü göndərildi: %s", day.isoformat())


def topic_items(name: str) -> list[dict]:
    return [item for item in PROVERBS if name in item["movzu"]]


def topic_menu_markup() -> InlineKeyboardMarkup:
    rows = []
    row = []
    for index, name in enumerate(TOPICS):
        count = len(topic_items(name))
        row.append(InlineKeyboardButton(f"{name} ({count})", callback_data=f"t:{index}:0"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows)


def topic_page(name: str, page: int, page_size: int = 15) -> tuple[str, int, int]:
    found = topic_items(name)
    total = len(found)
    pages = max(1, (total + page_size - 1) // page_size)
    page = max(0, min(page, pages - 1))
    start = page * page_size
    chunk = found[start : start + page_size]
    lines = [
        f"Mövzu: {name}",
        f"{total} atalar sözü. Səhifə {page + 1}/{pages}.",
        "",
    ]
    for number, item in enumerate(chunk, start=start + 1):
        lines.append(format_proverb(item, sira=number))
        lines.append("")
    return "\n".join(lines).strip(), page, pages


def topic_nav(index: int, page: int, pages: int) -> InlineKeyboardMarkup:
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("← Geri", callback_data=f"t:{index}:{page - 1}"))
    if page + 1 < pages:
        nav.append(InlineKeyboardButton("İrəli →", callback_data=f"t:{index}:{page + 1}"))
    rows = []
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("Mövzular", callback_data="t:menu")])
    return InlineKeyboardMarkup(rows)


async def show_topics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Mövzu seç.", reply_markup=topic_menu_markup())
    return ConversationHandler.END


async def on_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    if data == "t:menu":
        await query.edit_message_text("Mövzu seç.", reply_markup=topic_menu_markup())
        return
    parts = data.split(":")
    try:
        index = int(parts[1])
        page = int(parts[2]) if len(parts) > 2 else 0
        name = TOPICS[index]
    except (IndexError, ValueError):
        await query.message.reply_text("Bu mövzu tapılmadı.", reply_markup=MENU_KEYBOARD)
        return
    text, page, pages = topic_page(name, page)
    await query.edit_message_text(text, reply_markup=topic_nav(index, page, pages))


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


async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = (update.inline_query.query or "").strip()
    if query:
        found = [item for _score, item in search_by_keyword(query, limit=8)]
    else:
        found = random.sample(PROVERBS, k=min(5, len(PROVERBS)))
    results = [
        InlineQueryResultArticle(
            id=str(item["id"]),
            title=item["text"],
            description=item["mena"],
            input_message_content=InputTextMessageContent(format_proverb(item)),
        )
        for item in found
    ]
    await update.inline_query.answer(results, cache_time=5, is_personal=False)


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
            CommandHandler("quiz", ask_quiz),
            MessageHandler(filters.Regex(r"^(🧩 Quiz|Quiz)$"), ask_quiz),
        ],
        states={
            ACAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_keyword)],
            HEKAYE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_story)],
            QUIZ: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_quiz)],
        },
        fallbacks=[
            CommandHandler("legv", cancel),
            CommandHandler("start", start),
            CommandHandler("komek", help_cmd),
            CommandHandler("help", help_cmd),
            CommandHandler("tesaduf", random_proverb),
            CommandHandler("movzu", show_topics),
            CommandHandler("gun", daily_proverb),
            CommandHandler("quiz", ask_quiz),
        ],
        allow_reentry=True,
    )

    app.add_handler(conv)
    app.add_handler(InlineQueryHandler(inline_query))
    app.add_handler(CommandHandler("komek", help_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("tesaduf", random_proverb))
    app.add_handler(CommandHandler("movzu", show_topics))
    app.add_handler(CommandHandler("gun", daily_proverb))
    app.add_handler(CommandHandler("quiz", ask_quiz))
    app.add_handler(CallbackQueryHandler(on_topic, pattern=r"^t:(menu|\d+:\d+)$"))
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
    if application.job_queue is None:
        logger.error("Günlük göndəriş işə düşmədi.")
    else:
        application.job_queue.run_daily(
            post_daily_to_channel,
            time=time(9, 0, tzinfo=BAKI),
            name="gunun-sozu",
        )
        logger.info("Kanal: %s, hər gün 09:00", CHANNEL)
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        bootstrap_retries=-1,
        timeout=20,
    )


if __name__ == "__main__":
    main()
