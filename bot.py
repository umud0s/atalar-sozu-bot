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
    TypeHandler,
    filters,
)
from telegram.error import Forbidden, RetryAfter, TelegramError
from telegram.request import HTTPXRequest

from axtaris import concepts, stems
from istifade import Usage, backup_zip, make_backup
from kart import render_card

load_dotenv()

LOGGING_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
logging.basicConfig(format=LOGGING_FORMAT, level=logging.INFO)
logger = logging.getLogger("atalar")

ACAR, HEKAYE, QUIZ = range(3)

DATA_PATH = Path(__file__).with_name("proverbs.json")
STATS_PATH = Path(__file__).with_name("quiz_stats.json")
_stats_lock = asyncio.Lock()
SUBS_PATH = Path(__file__).with_name("abuneler.json")
_subs_lock = asyncio.Lock()


def load_proverbs() -> list[dict]:
    with DATA_PATH.open(encoding="utf-8") as f:
        data = json.load(f)
    return data["proverbs"]


PROVERBS = load_proverbs()
CHANNEL = "@atalarimizinsozu"
PROVERB_BY_ID = {item["id"]: item for item in PROVERBS}
STEM_INDEX = {item["id"]: stems(item["text"] + " " + item["mena"]) for item in PROVERBS}
TEXT_STEMS = {item["id"]: stems(item["text"]) for item in PROVERBS}
TAG_INDEX = {item["id"]: set(item["acar"]) for item in PROVERBS}
REPORTS_PATH = Path(__file__).with_name("xetalar.jsonl")
USAGE = Usage()
ACTION_NAMES = {
    "🔑 Açar söz": "Açar söz", "📖 Hekayə": "Hekayə", "🎲 Təsadüfi": "Təsadüfi",
    "📚 Mövzular": "Mövzular", "🌅 Günün sözü": "Günün sözü", "🧩 Quiz": "Quiz",
    "🔔 Hər gün söz": "Hər gün söz", "ℹ️ Kömək": "Kömək", "⏭ Pas": "Quiz",
}
CALLBACK_NAMES = {"t": "Mövzular", "k": "Kart şəkli", "o": "Oxşar sözlər", "x": "Səhv bildir"}
_reports_lock = asyncio.Lock()
BAKI = timezone(timedelta(hours=4))

MENU_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["🔑 Açar söz", "📖 Hekayə"],
        ["🎲 Təsadüfi", "📚 Mövzular"],
        ["🌅 Günün sözü", "🧩 Quiz"],
        ["🔔 Hər gün söz", "ℹ️ Kömək"],
    ],
    resize_keyboard=True,
)
QUIZ_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["⏭ Pas"],
        ["🔑 Açar söz", "📖 Hekayə"],
        ["🎲 Təsadüfi", "📚 Mövzular"],
        ["🌅 Günün sözü", "🧩 Quiz"],
        ["🔔 Hər gün söz", "ℹ️ Kömək"],
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
    "Dil və söz",
    "Var-dövlət",
    "Dərd və səbr",
    "Haqq və ədalət",
    "Sevgi",
    "Qonaqpərvərlik",
    "İgidlik",
    "Tamah",
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


def share_markup(item: dict, card: bool = True) -> InlineKeyboardMarkup:
    row = [InlineKeyboardButton("📤 Dosta göndər", switch_inline_query=f"#{item['id']}")]
    if not card:
        return InlineKeyboardMarkup([row])
    row.append(InlineKeyboardButton("🖼 Kart şəkli", callback_data=f"k:{item['id']}"))
    return InlineKeyboardMarkup(
        [
            row,
            [
                InlineKeyboardButton("🔁 Oxşar sözlər", callback_data=f"o:{item['id']}"),
                InlineKeyboardButton("⚠️ Səhv bildir", callback_data=f"x:{item['id']}"),
            ],
        ]
    )


def stem_score(query_roots: set[str], query_tags: set[str], item_id: int) -> int:
    roots = STEM_INDEX[item_id]
    score = 0
    for root in query_roots:
        if root in TEXT_STEMS[item_id]:
            score += 6
        elif root in roots:
            score += 4
        elif len(root) >= 4 and any(r.startswith(root) or root.startswith(r) for r in roots if len(r) >= 4):
            score += 2
    score += len(query_tags & TAG_INDEX[item_id])
    return score


def similar_items(item: dict, limit: int = 3) -> list[dict]:
    mine = STEM_INDEX[item["id"]]
    topics = set(item["movzu"])
    scored = []
    for other in PROVERBS:
        if other["id"] == item["id"]:
            continue
        common = len(mine & STEM_INDEX[other["id"]])
        if not common:
            continue
        score = 3 * common + 2 * len(topics & set(other["movzu"]))
        scored.append((score, other["id"], other))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [other for _s, _i, other in scored[:limit]]


def search_by_keyword(query: str, limit: int = 8) -> list[tuple[int, dict]]:
    q_norm = normalize(query)
    q_tokens = tokens(query)
    if not q_norm:
        return []
    q_roots = stems(query)
    q_tags = concepts(q_roots)

    scored: list[tuple[int, dict]] = []
    for item in PROVERBS:
        haystack = " ".join([item["text"], item["mena"], " ".join(item["movzu"])])
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
        score += stem_score(q_roots, q_tags, item["id"])
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
        "• Quiz — çatışmayan sözü tamamla. Cavabdan sonra sənin statistikən görünür.\n"
        "• Hər gün söz — hər səhər saat 09:00-da günün sözünü sənə göndərim."
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
        "/abune — hər gün saat 09:00-da günün sözünü al və ya dayandır\n"
        "/legv — axtarışı dayandır\n\n"
        "Təsadüfi söz və günün sözü altında iki düymə var: «📤 Dosta göndər» sözü istənilən söhbətə göndərir, «🖼 Kart şəkli» paylaşmaq üçün şəkil hazırlayır.\n\n"
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
        reply_markup=share_markup(item),
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
    if text in {"🔔 Hər gün söz", "Hər gün söz"}:
        return await toggle_subscription(update, context)
    return None


async def handle_keyword(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    routed = await route_menu(update, context)
    if routed is not None:
        return routed
    query = (update.message.text or "").strip()
    USAGE.query(query)
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


def daily_item(day: datetime.date | None = None) -> dict:
    day = day or datetime.now(BAKI).date()
    return PROVERBS[day.toordinal() % len(PROVERBS)]


def daily_text(day: datetime.date | None = None) -> str:
    day = day or datetime.now(BAKI).date()
    item = daily_item(day)
    return (
        f"Günün sözü, {day.strftime('%d.%m.%Y')}:\n\n"
        + format_proverb(item)
        + "\n\nDaha çoxu üçün: @AtalarSozleri_bot"
    )


async def daily_proverb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(daily_text(), reply_markup=share_markup(daily_item()))
    return ConversationHandler.END


async def post_daily_to_channel(context: ContextTypes.DEFAULT_TYPE) -> None:
    day = datetime.now(BAKI).date()
    item = daily_item(day)
    markup = share_markup(item, card=False)
    try:
        await context.bot.send_photo(
            chat_id=CHANNEL,
            photo=render_card(item["text"], item["mena"]),
            caption=daily_text(day),
            reply_markup=markup,
        )
    except Exception as exc:  # şəkil alınmasa, mətn yenə getsin
        logger.warning("Kanal kartı göndərilmədi, mətn göndərilir: %s", exc)
        await context.bot.send_message(chat_id=CHANNEL, text=daily_text(day), reply_markup=markup)
    logger.info("Kanala günün sözü göndərildi: %s", day.isoformat())


POLL_LETTERS = str.maketrans({"I": "ı", "İ": "i"})


def az_lower(word: str) -> str:
    return word.translate(POLL_LETTERS).lower()


def poll_word(item: dict) -> str | None:
    match = _quiz_word(item)
    if match is None:
        return None
    word = match.group()
    return az_lower(word) if match.start() == 0 else word


def make_channel_poll() -> tuple[str, list[str], int, str] | None:
    for _ in range(50):
        item = random.choice(PROVERBS)
        made = make_quiz(item)
        answer = poll_word(item)
        if made is None or answer is None:
            continue
        shown = made[0]
        options = [answer]
        seen = {normalize(answer)}
        for _ in range(200):
            word = poll_word(random.choice(PROVERBS))
            if word is None:
                continue
            key = normalize(word)
            if key in seen or abs(len(word) - len(answer)) > 3:
                continue
            seen.add(key)
            options.append(word)
            if len(options) == 4:
                break
        if len(options) < 4:
            continue
        random.shuffle(options)
        question = f"Atalar sözünü tamamla:\n«{shown}»"
        if len(question) > 300:
            continue
        return question, options, options.index(answer), item["mena"][:200]
    return None


async def post_weekly_poll(context: ContextTypes.DEFAULT_TYPE) -> None:
    made = make_channel_poll()
    if made is None:
        logger.warning("Həftəlik quiz hazırlanmadı.")
        return
    question, options, correct, explanation = made
    await context.bot.send_poll(
        chat_id=CHANNEL,
        question=question,
        options=options,
        type="quiz",
        correct_option_id=correct,
        explanation=explanation,
        is_anonymous=True,
    )
    logger.info("Kanala həftəlik quiz göndərildi.")


def admin_id() -> int | None:
    raw = os.getenv("ADMIN_ID", "").strip()
    return int(raw) if raw.lstrip("-").isdigit() else None


def action_name(update: Update) -> str:
    if update.inline_query:
        return "Inline axtarış"
    if update.callback_query:
        return CALLBACK_NAMES.get((update.callback_query.data or "?")[0], "Düymə")
    message = update.effective_message
    text = (message.text or "").strip() if message else ""
    if text.startswith("/"):
        return text.split()[0].split("@")[0]
    if text in ACTION_NAMES:
        return ACTION_NAMES[text]
    return "Mətn" if text else "Digər"


async def track(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat is not None and chat.type == "channel":
        return
    user = update.effective_user
    try:
        USAGE.hit(user.id if user else None, action_name(update), datetime.now(BAKI).date())
    except Exception as exc:  # statistika botu dayandırmamalıdır
        logger.warning("Statistika yazılmadı: %s", exc)


async def flush_usage(context: ContextTypes.DEFAULT_TYPE | None = None) -> None:
    try:
        USAGE.save()
    except OSError as exc:
        logger.warning("istifade.json yazılmadı: %s", exc)


def is_admin(update: Update) -> bool:
    owner = admin_id()
    return owner is not None and update.effective_user is not None and update.effective_user.id == owner


def quiz_totals() -> dict:
    if not STATS_PATH.exists():
        return {}
    try:
        data = json.loads(STATS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    total = {"duz": 0, "sehv": 0, "pas": 0}
    for row in data.values():
        for key in total:
            total[key] += int(row.get(key, 0))
    return total


async def stat_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update):
        await update.message.reply_text("Bu əmr yalnız bot sahibi üçündür.", reply_markup=MENU_KEYBOARD)
        return ConversationHandler.END
    reports = 0
    if REPORTS_PATH.exists():
        reports = sum(1 for line in REPORTS_PATH.read_text(encoding="utf-8").splitlines() if line.strip())
    text = USAGE.report(datetime.now(BAKI).date(), len(load_subscribers()), reports, quiz_totals())
    await update.message.reply_text(text, reply_markup=MENU_KEYBOARD)
    return ConversationHandler.END


async def send_backup(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> bool:
    await flush_usage()
    archive = backup_zip(datetime.now(BAKI).date())
    if archive is None:
        return False
    await context.bot.send_document(chat_id=chat_id, document=archive, caption="Botun ehtiyat nüsxəsi.")
    return True


async def backup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update):
        await update.message.reply_text("Bu əmr yalnız bot sahibi üçündür.", reply_markup=MENU_KEYBOARD)
        return ConversationHandler.END
    if not await send_backup(context, update.effective_chat.id):
        await update.message.reply_text("Hələ yedəklənəcək fayl yoxdur.", reply_markup=MENU_KEYBOARD)
    return ConversationHandler.END


async def daily_backup(context: ContextTypes.DEFAULT_TYPE) -> None:
    await flush_usage()
    today = datetime.now(BAKI).date()
    folder = make_backup(today)
    logger.info("Serverdə ehtiyat nüsxə: %s", folder)
    owner = admin_id()
    if owner and today.weekday() == 0:
        try:
            await send_backup(context, owner)
        except TelegramError as exc:
            logger.warning("Ehtiyat nüsxə sahibə göndərilmədi: %s", exc)


async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(f"Sənin Telegram ID-n: {update.effective_user.id}", reply_markup=MENU_KEYBOARD)
    return ConversationHandler.END


async def on_similar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    try:
        item = PROVERB_BY_ID[int((query.data or "").split(":")[1])]
    except (IndexError, KeyError, ValueError):
        await query.answer("Bu söz tapılmadı.")
        return
    found = similar_items(item)
    await query.answer()
    if not found:
        await context.bot.send_message(chat_id=query.message.chat_id, text="Bu sözə oxşar söz tapılmadı.")
        return
    lines = [f"«{item['text']}» sözünə oxşar atalar sözləri:", ""]
    for number, other in enumerate(found, start=1):
        lines.append(format_proverb(other, sira=number))
        lines.append("")
    await context.bot.send_message(chat_id=query.message.chat_id, text="\n".join(lines).strip())


REPORT_KINDS = {"m": "Mövzu səhvdir", "i": "İzah səhvdir"}


async def on_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    parts = (query.data or "").split(":")
    try:
        item = PROVERB_BY_ID[int(parts[1])]
    except (IndexError, KeyError, ValueError):
        await query.answer("Bu söz tapılmadı.")
        return
    if len(parts) == 2:
        await query.answer()
        await query.edit_message_reply_markup(
            InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("Mövzu səhvdir", callback_data=f"x:{item['id']}:m"),
                        InlineKeyboardButton("İzah səhvdir", callback_data=f"x:{item['id']}:i"),
                    ],
                    [InlineKeyboardButton("← Geri", callback_data=f"x:{item['id']}:geri")],
                ]
            )
        )
        return
    kind = parts[2]
    if kind in REPORT_KINDS:
        row = {
            "vaxt": datetime.now(BAKI).isoformat(timespec="seconds"),
            "id": item["id"],
            "nov": REPORT_KINDS[kind],
            "istifadeci": update.effective_user.id,
            "text": item["text"],
            "mena": item["mena"],
            "movzu": item["movzu"],
        }
        async with _reports_lock:
            with REPORTS_PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        await query.answer("Təşəkkür edirəm. Bildirişin qeydə alındı.", show_alert=True)
        owner = admin_id()
        if owner:
            try:
                await context.bot.send_message(
                    chat_id=owner,
                    text=(
                        f"Səhv bildirişi: {REPORT_KINDS[kind]}\n"
                        f"id {item['id']}: «{item['text']}»\n"
                        f"Məna: {item['mena']}\n"
                        f"Mövzu: {', '.join(item['movzu'])}"
                    ),
                )
            except TelegramError as exc:
                logger.warning("Admin bildirişi getmədi: %s", exc)
    else:
        await query.answer()
    await query.edit_message_reply_markup(share_markup(item))


async def on_card(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    try:
        item = PROVERB_BY_ID[int((query.data or "").split(":")[1])]
    except (IndexError, KeyError, ValueError):
        await query.answer("Bu söz tapılmadı.")
        return
    await query.answer("Kart hazırlanır…")
    await context.bot.send_photo(
        chat_id=query.message.chat_id,
        photo=render_card(item["text"], item["mena"]),
        caption=f"«{item['text']}»\n\nDaha çoxu üçün: @AtalarSozleri_bot",
        reply_markup=share_markup(item, card=False),
    )


def load_subscribers() -> set[int]:
    if not SUBS_PATH.exists():
        return set()
    try:
        return {int(x) for x in json.loads(SUBS_PATH.read_text(encoding="utf-8"))}
    except (json.JSONDecodeError, TypeError, ValueError):
        logger.warning("abuneler.json oxunmadı, boş siyahı götürülür.")
        return set()


def save_subscribers(subs: set[int]) -> None:
    temporary = SUBS_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(sorted(subs)) + "\n", encoding="utf-8")
    temporary.replace(SUBS_PATH)


async def toggle_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = update.effective_chat.id
    async with _subs_lock:
        subs = load_subscribers()
        if chat_id in subs:
            subs.discard(chat_id)
            text = (
                "Gündəlik göndəriş dayandırıldı.\n"
                "Yenidən başlamaq üçün «🔔 Hər gün söz» düyməsini bas."
            )
        else:
            subs.add(chat_id)
            text = (
                "Hazırdır. Hər gün saat 09:00-da günün sözünü sənə göndərəcəyəm.\n"
                "Dayandırmaq üçün «🔔 Hər gün söz» düyməsini yenidən bas."
            )
        save_subscribers(subs)
    await update.message.reply_text(text, reply_markup=MENU_KEYBOARD)
    return ConversationHandler.END


async def send_daily_to_subscribers(context: ContextTypes.DEFAULT_TYPE) -> None:
    text = daily_text()
    markup = share_markup(daily_item())
    async with _subs_lock:
        subs = load_subscribers()
    sent, gone = 0, set()
    for chat_id in sorted(subs):
        try:
            await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=markup)
            sent += 1
        except RetryAfter as exc:
            await asyncio.sleep(exc.retry_after + 1)
            try:
                await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=markup)
                sent += 1
            except TelegramError as again:
                logger.warning("Abunəçiyə göndərilmədi %s: %s", chat_id, again)
        except Forbidden:
            gone.add(chat_id)
        except TelegramError as exc:
            logger.warning("Abunəçiyə göndərilmədi %s: %s", chat_id, exc)
        await asyncio.sleep(0.05)
    if gone:
        async with _subs_lock:
            save_subscribers(load_subscribers() - gone)
    logger.info("Abunəçilərə günün sözü: göndərildi %s, botu bloklayan %s", sent, len(gone))


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


async def reject_non_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    try:
        await message.delete()
    except TelegramError as exc:
        logger.info("Mətn olmayan mesaj silinmədi: %s", exc)
    await context.bot.send_message(
        chat_id=message.chat_id,
        text="Bot yalnız mətn qəbul edir. Şəkil, fayl, səs və stiker göndərmək olmaz.",
        reply_markup=MENU_KEYBOARD,
    )


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
    exact = re.fullmatch(r"#(\d+)", query)
    if exact and int(exact.group(1)) in PROVERB_BY_ID:
        found = [PROVERB_BY_ID[int(exact.group(1))]]
    elif query:
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
        .post_shutdown(flush_usage)
        .build()
    )

    app.add_handler(TypeHandler(Update, track), group=-1)

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
            CommandHandler("abune", toggle_subscription),
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
    app.add_handler(CommandHandler("abune", toggle_subscription))
    app.add_handler(CallbackQueryHandler(on_topic, pattern=r"^t:(menu|\d+:\d+)$"))
    app.add_handler(CallbackQueryHandler(on_card, pattern=r"^k:\d+$"))
    app.add_handler(CallbackQueryHandler(on_similar, pattern=r"^o:\d+$"))
    app.add_handler(CallbackQueryHandler(on_report, pattern=r"^x:\d+(:(m|i|geri))?$"))
    app.add_handler(CommandHandler("menim_id", my_id))
    app.add_handler(CommandHandler("stat", stat_cmd))
    app.add_handler(CommandHandler("yedek", backup_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_text_router))
    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & ~filters.TEXT & ~filters.COMMAND & ~filters.StatusUpdate.ALL,
            reject_non_text,
        )
    )
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
        application.job_queue.run_daily(
            send_daily_to_subscribers,
            time=time(9, 0, 30, tzinfo=BAKI),
            name="abuneler",
        )
        application.job_queue.run_daily(
            post_weekly_poll,
            time=time(12, 0, tzinfo=BAKI),
            days=(0,),
            name="heftelik-quiz",
        )
        logger.info("Kanalda həftəlik quiz: bazar günü 12:00")
        application.job_queue.run_repeating(flush_usage, interval=120, first=120, name="statistika")
        application.job_queue.run_daily(daily_backup, time=time(3, 0, tzinfo=BAKI), name="yedek")
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        bootstrap_retries=-1,
        timeout=20,
    )


if __name__ == "__main__":
    main()
