"""Axtarış üçün sadə kök ayırma və anlayış qrupları."""

from __future__ import annotations

import re

_FOLD = str.maketrans({"ə": "e", "ı": "i", "ö": "o", "ü": "u", "ğ": "g", "ş": "s", "ç": "c", "İ": "i", "I": "i"})

STOP = {
    "bir", "bu", "da", "de", "ve", "ile", "ucun", "sonra", "amma", "ki", "cox", "olan",
    "olsun", "hec", "artiq", "indi", "ona", "bunu", "bele", "ele", "nece", "cunki",
    "lakin", "hem", "qeder", "mene", "sene", "oz", "ozu", "ozun", "idi", "imis", "gore",
    "kimi", "hara", "ne", "kim", "her", "var", "yox", "deyil", "olar", "olur", "edir",
    "adam", "insan", "kes", "sey", "onu", "onun", "mən", "men", "sen", "biz", "siz",
    "daha", "yene", "bele", "hamı", "hami", "elə", "olmaz", "etmir", "olmur",
}

# Sondan qoparılan şəkilçilər (uzundan qısaya).
SUFFIXES = (
    "larindan", "lerinden", "larinin", "lerinin", "larina", "lerine", "larini", "lerini",
    "lardan", "lerden", "larda", "lerde", "lari", "leri", "lar", "ler",
    "liqla", "lukle", "liq", "luq", "lik", "luk", "siz", "suz", "li", "lu",
    "sinin", "sunun", "nin", "nun", "inin", "unun",
    "dan", "den", "nan", "nen", "da", "de",
    "sini", "sunu", "ni", "nu", "si", "su",
    "ina", "ine", "una", "une", "ya", "ye",
    "maq", "mek", "maz", "mez", "mir", "mur", "mis", "mus",
    "acaq", "ecek", "ar", "er", "ir", "ur", "an", "en", "di", "du", "ib", "ub",
    "la", "le", "in", "un", "i", "u", "a", "e",
)

CONCEPTS = [
    ({"dost", "yoldas", "asna", "refiq"}, ["dost", "dostluq", "yoldas"]),
    ({"dusmen", "kin", "dava", "savas"}, ["dusmen", "dava"]),
    ({"zehmet", "isle", "calis", "emek", "isci", "tenbel", "is"}, ["zehmet", "is", "emek"]),
    ({"pul", "dovlet", "varli", "mal", "kasib", "yoxsul", "borc", "qizil", "xerc"}, ["pul", "var", "dovlet", "kasib"]),
    ({"elm", "bilik", "oxu", "savad", "alim", "oyren", "muellim", "kitab"}, ["elm", "bilik", "oyrenmek"]),
    ({"soz", "dil", "danis", "sus", "dinme"}, ["soz", "dil", "danismaq"]),
    ({"ana", "ata", "ovlad", "usaq", "ogul", "qiz", "bala", "qardas", "baci", "aile", "nesil"}, ["aile", "ovlad"]),
    ({"er", "arvad", "gelin", "qaynana", "evlen"}, ["aile", "evlilik"]),
    ({"qonaq", "sufre"}, ["qonaq", "qonaqperverlik"]),
    ({"qonsu"}, ["qonsu"]),
    ({"yalan", "aldat", "hiyle"}, ["yalan", "hiyle"]),
    ({"dogru", "duz", "haqq", "edalet", "zulm", "zalim"}, ["haqq", "edalet", "dogruluq"]),
    ({"sebr", "sebir", "dozum"}, ["sebir"]),
    ({"derd", "qem", "kedr", "agla", "bela"}, ["derd", "qem"]),
    ({"qorx", "igid", "merd", "cesur", "qorxaq"}, ["igidlik", "qorxu"]),
    ({"namerd", "xain", "xeyanet"}, ["namerd", "xeyanet"]),
    ({"tamah", "acgoz", "doymaz", "xesis", "paxil"}, ["tamah", "xesislik"]),
    ({"vaxt", "zaman", "tez", "gec", "sabah", "bugun", "fursət", "fursat", "fürsət"}, ["vaxt", "fursət"]),
    ({"birlik", "el", "xalq", "camaat", "birlesen"}, ["birlik", "el"]),
    ({"veten", "yurd", "qerib", "qurbet"}, ["veten", "qeriblik"]),
    ({"sevgi", "sev", "esq", "asiq", "yar", "konul"}, ["sevgi", "esq"]),
    ({"agil", "agilli", "deli", "axmaq", "nadan", "cahil", "dusun"}, ["agil", "nadanliq"]),
    ({"ehtiyat", "tedbir"}, ["ehtiyat", "tedbir"]),
    ({"hormet", "boyuk", "agsaqqal"}, ["hormet", "boyuk"]),
    ({"yaxsiliq", "xeyir", "sexavet", "comerd"}, ["yaxsiliq", "xeyir"]),
    ({"pislik", "ser"}, ["pislik"]),
    ({"tale", "qismet", "felek", "ruzi"}, ["tale", "qismet"]),
    ({"olum", "ecel", "olu"}, ["olum"]),
    ({"saglam", "xeste", "azar", "derman"}, ["saglamliq", "xestelik"]),
    ({"tamahkar"}, ["tamah"]),
    ({"acliq", "tox", "corek", "corey", "bereket"}, ["bereket", "corek"]),
    ({"hirs", "qezeb", "aciq"}, ["hirs", "qezeb"]),
    ({"heya", "abir", "utan", "edeb", "namus"}, ["heya", "edeb"]),
]


def fold(text: str) -> str:
    text = text.translate(_FOLD).lower()
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def stem(word: str) -> str:
    word = fold(word)
    for _ in range(3):
        for suffix in SUFFIXES:
            keep = 4 if len(suffix) <= 2 and suffix not in ("li", "lu") else 3
            if word.endswith(suffix) and len(word) - len(suffix) >= keep:
                word = word[: -len(suffix)]
                break
        else:
            break
    if word.endswith("g") and len(word) >= 4:
        word = word[:-1] + "q"
    return word


def stems(text: str) -> set[str]:
    out = set()
    for word in fold(text).split():
        if len(word) < 3 or word in STOP:
            continue
        root = stem(word)
        if len(root) >= 3 and root not in STOP:
            out.add(root)
    return out


def concepts(roots: set[str]) -> set[str]:
    out = set()
    for triggers, tags in CONCEPTS:
        for root in roots:
            if any(root == t or (len(t) >= 4 and root.startswith(t)) or (len(root) >= 4 and t.startswith(root)) for t in triggers):
                out.update(fold(tag) for tag in tags)
                break
    return out
