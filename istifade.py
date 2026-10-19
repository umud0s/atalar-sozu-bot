"""İstifadə statistikası və ehtiyat nüsxələr."""

from __future__ import annotations

import json
import logging
import shutil
import zipfile
from collections import Counter
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path

logger = logging.getLogger("atalar")

BASE = Path(__file__).parent
USAGE_PATH = BASE / "istifade.json"
BACKUP_DIR = BASE / "yedekler"
BACKUP_FILES = ("quiz_stats.json", "abuneler.json", "istifade.json", "xetalar.jsonl")
KEEP_DAYS = 14
TOP_QUERIES = 300


class Usage:
    def __init__(self) -> None:
        self.users: dict[str, dict] = {}
        self.days: dict[str, dict] = {}
        self.queries: Counter[str] = Counter()
        self.dirty = False
        self.load()

    def load(self) -> None:
        if not USAGE_PATH.exists():
            return
        try:
            data = json.loads(USAGE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("istifade.json oxunmadı: %s", exc)
            return
        self.users = data.get("users", {})
        self.days = data.get("days", {})
        self.queries = Counter(data.get("queries", {}))

    def save(self) -> None:
        if not self.dirty:
            return
        cutoff = (date.today() - timedelta(days=90)).isoformat()
        self.days = {d: v for d, v in self.days.items() if d >= cutoff}
        data = {
            "users": self.users,
            "days": self.days,
            "queries": dict(self.queries.most_common(TOP_QUERIES)),
        }
        temporary = USAGE_PATH.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(USAGE_PATH)
        self.dirty = False

    def hit(self, user_id: int | None, action: str, today: date) -> None:
        day = today.isoformat()
        row = self.days.setdefault(day, {"actions": {}, "users": [], "new": 0})
        row["actions"][action] = row["actions"].get(action, 0) + 1
        if user_id is not None:
            key = str(user_id)
            if key not in self.users:
                self.users[key] = {"ilk": day, "son": day}
                row["new"] += 1
            else:
                self.users[key]["son"] = day
            if user_id not in row["users"]:
                row["users"].append(user_id)
        self.dirty = True

    def query(self, text: str) -> None:
        text = " ".join(text.lower().split())[:40]
        if text:
            self.queries[text] += 1
            self.dirty = True

    def report(self, today: date, subscribers: int, reports: int, quiz: dict) -> str:
        day = today.isoformat()
        week = {(today - timedelta(days=i)).isoformat() for i in range(7)}
        month = {(today - timedelta(days=i)).isoformat() for i in range(30)}
        active_today = len(self.days.get(day, {}).get("users", []))
        active_week = len({u for d in week for u in self.days.get(d, {}).get("users", [])})
        active_month = len({u for d in month for u in self.days.get(d, {}).get("users", [])})
        new_week = sum(self.days.get(d, {}).get("new", 0) for d in week)
        actions = Counter()
        for d in week:
            actions.update(self.days.get(d, {}).get("actions", {}))
        lines = [
            f"Statistika, {today.strftime('%d.%m.%Y')}",
            "",
            f"İstifadəçi, cəmi: {len(self.users)}",
            f"Bu gün aktiv: {active_today}",
            f"Son 7 gün aktiv: {active_week}",
            f"Son 30 gün aktiv: {active_month}",
            f"Son 7 gündə yeni: {new_week}",
            f"Hər gün söz abunəçisi: {subscribers}",
            f"Səhv bildirişi, cəmi: {reports}",
            f"Quiz cavabları: düzgün {quiz.get('duz', 0)}, səhv {quiz.get('sehv', 0)}, pas {quiz.get('pas', 0)}",
            "",
            "Son 7 gündə ən çox istifadə olunan:",
        ]
        for name, count in actions.most_common(8):
            lines.append(f"• {name}: {count}")
        if self.queries:
            lines += ["", "Ən çox axtarılan sözlər:"]
            for text, count in self.queries.most_common(10):
                lines.append(f"• {text}: {count}")
        return "\n".join(lines)


def make_backup(today: date) -> Path | None:
    target = BACKUP_DIR / today.isoformat()
    copied = 0
    for name in BACKUP_FILES:
        source = BASE / name
        if source.exists():
            target.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target / name)
            copied += 1
    old = sorted(p for p in BACKUP_DIR.glob("*") if p.is_dir()) if BACKUP_DIR.exists() else []
    for folder in old[:-KEEP_DAYS]:
        shutil.rmtree(folder, ignore_errors=True)
    return target if copied else None


def backup_zip(today: date) -> BytesIO | None:
    out = BytesIO()
    added = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in BACKUP_FILES:
            source = BASE / name
            if source.exists():
                zf.write(source, arcname=name)
                added += 1
    if not added:
        return None
    out.seek(0)
    out.name = f"atalar-yedek-{today.isoformat()}.zip"
    return out
