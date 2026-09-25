#!/usr/bin/env python3
"""proverbs.json-a yeni atalar sözü əlavə et."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "proverbs.json"


def load() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


def save(data: dict) -> None:
    data["meta"]["say"] = len(data["proverbs"])
    DATA.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    if len(sys.argv) < 5:
        print(
            "İstifadə:\n"
            "  python tools/add_proverb.py "
            "\"Atalar sözü\" \"Qısa məna\" "
            "\"acar1,acar2\" \"movzu1,movzu2\""
        )
        sys.exit(1)

    text, mena, acar_raw, movzu_raw = sys.argv[1:5]
    data = load()
    next_id = max(p["id"] for p in data["proverbs"]) + 1
    item = {
        "id": next_id,
        "text": text.strip(),
        "mena": mena.strip(),
        "acar": [x.strip() for x in acar_raw.split(",") if x.strip()],
        "movzu": [x.strip() for x in movzu_raw.split(",") if x.strip()],
    }
    data["proverbs"].append(item)
    save(data)
    print(f"Əlavə olundu: #{next_id} — {item['text']}")
    print(f"Ümumi say: {data['meta']['say']}")


if __name__ == "__main__":
    main()
