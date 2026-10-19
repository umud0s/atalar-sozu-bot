"""Atalar sözü üçün paylaşıla bilən kart şəkli."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTS = Path(__file__).with_name("fonts")
WIDTH, HEIGHT = 1080, 1350
MARGIN = 96

BG = (30, 58, 52)
TEXT = (244, 235, 217)
SOFT = (201, 211, 200)
GOLD = (201, 164, 92)


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / name), size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines: list[str] = []
    line = ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= width:
            line = trial
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def _fit(draw, text, name, sizes, width, max_height, spacing):
    for size in sizes:
        font = _font(name, size)
        lines = _wrap(draw, text, font, width)
        height = len(lines) * int(size * spacing)
        if height <= max_height:
            return font, lines, int(size * spacing)
    font = _font(name, sizes[-1])
    return font, _wrap(draw, text, font, width), int(sizes[-1] * spacing)


def render_card(text: str, mena: str, footer: str = "@AtalarSozleri_bot") -> BytesIO:
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    inner = WIDTH - 2 * MARGIN

    draw.rectangle([40, 40, WIDTH - 40, HEIGHT - 40], outline=GOLD, width=3)
    draw.text((MARGIN, 120), "ATALAR SÖZÜ", font=_font("DejaVuSans-Bold.ttf", 34), fill=GOLD)

    top, bottom = 300, HEIGHT - 190
    body_font, body, body_step = _fit(
        draw, text, "DejaVuSerif-Bold.ttf", range(88, 39, -4), inner, 560, 1.3
    )
    body_height = len(body) * body_step
    mena_font, mena_lines, mena_step = _fit(
        draw, mena, "DejaVuSans.ttf", range(42, 25, -2), inner, bottom - top - body_height - 84, 1.4
    )
    total = body_height + 84 + len(mena_lines) * mena_step
    y = top + max(0, (bottom - top - total) // 2)
    draw.text((MARGIN - 8, y - 200), "“", font=_font("DejaVuSerif-Bold.ttf", 180), fill=GOLD)

    for line in body:
        draw.text((MARGIN, y), line, font=body_font, fill=TEXT)
        y += body_step

    y += 40
    draw.line([MARGIN, y, MARGIN + 160, y], fill=GOLD, width=4)
    y += 44

    for line in mena_lines:
        draw.text((MARGIN, y), line, font=mena_font, fill=SOFT)
        y += mena_step

    footer_font = _font("DejaVuSans-Bold.ttf", 32)
    draw.text((MARGIN, HEIGHT - 140), footer, font=footer_font, fill=GOLD)

    out = BytesIO()
    image.save(out, format="PNG", optimize=True)
    out.seek(0)
    out.name = "atalar-sozu.png"
    return out
