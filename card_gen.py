import io
import os
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

CARDS_DIR = Path(__file__).parent / "output" / "cards"
CARD_W, CARD_H = 1080, 1350
IMAGE_H = 540

BG_COLOR = "#111111"
TEXT_COLOR = "#ffffff"
SUMMARY_COLOR = "#cccccc"
SOURCE_COLOR = "#888888"


def _load_font(size: int, bold: bool = False):
    candidates_bold = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    candidates_regular = [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in (candidates_bold if bold else candidates_regular):
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default(size=size)


def _fetch_image(url: str) -> Image.Image | None:
    if not url:
        return None
    try:
        resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content)).convert("RGB")
        return img
    except Exception:
        return None


def _cover_crop(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    src_w, src_h = img.size
    scale = max(target_w / src_w, target_h / src_h)
    new_w, new_h = int(src_w * scale), int(src_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return img.crop((left, top, left + target_w, top + target_h))


def _draw_pill(draw: ImageDraw.ImageDraw, text: str, x: int, y: int, color: str):
    font = _load_font(26)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad_x, pad_y = 22, 10
    draw.rounded_rectangle(
        [x, y, x + tw + pad_x * 2, y + th + pad_y * 2],
        radius=20,
        fill=color,
    )
    draw.text((x + pad_x, y + pad_y), text, font=font, fill="#ffffff")
    return y + th + pad_y * 2


def _draw_wrapped_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    x: int,
    y: int,
    max_width: int,
    font: ImageFont.FreeTypeFont,
    fill: str,
    line_spacing: int = 8,
    max_lines: int = 10,
) -> int:
    words = text.split()
    lines = []
    current = []
    for word in words:
        test = " ".join(current + [word])
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] > max_width and current:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))

    lines = lines[:max_lines]
    bbox = draw.textbbox((0, 0), "Ag", font=font)
    line_h = bbox[3] - bbox[1] + line_spacing
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += line_h
    return y


def generate_card(
    article_id: str,
    headline: str,
    summary: str,
    category: str,
    source: str,
    image_url: str | None = None,
) -> str:
    CARDS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CARDS_DIR / f"{article_id}.jpg"

    canvas = Image.new("RGB", (CARD_W, CARD_H), BG_COLOR)
    draw = ImageDraw.Draw(canvas)

    # --- image section ---
    article_img = _fetch_image(image_url)
    if article_img:
        cropped = _cover_crop(article_img, CARD_W, IMAGE_H)
        canvas.paste(cropped, (0, 0))
        gradient = Image.new("RGBA", (CARD_W, 120), (0, 0, 0, 0))
        for i in range(120):
            alpha = int(255 * (i / 120))
            ImageDraw.Draw(gradient).line([(0, i), (CARD_W, i)], fill=(17, 17, 17, alpha))
        canvas.paste(Image.new("RGB", (CARD_W, 120), BG_COLOR), (0, IMAGE_H - 120), gradient)
    else:
        canvas.paste(Image.new("RGB", (CARD_W, IMAGE_H), "#1a1a2e"), (0, 0))

    # --- text section ---
    pad = 60
    y = IMAGE_H + 30

    # app branding pill
    y = _draw_pill(draw, "BRIEFLY", pad, y, "#1a73e8") + 28

    # headline
    font_headline = _load_font(44, bold=True)
    y = _draw_wrapped_text(
        draw, headline, pad, y,
        max_width=CARD_W - pad * 2,
        font=font_headline,
        fill=TEXT_COLOR,
        line_spacing=10,
        max_lines=4,
    ) + 32

    # divider
    draw.line([(pad, y), (CARD_W - pad, y)], fill="#333333", width=2)
    y += 28

    # summary
    font_summary = _load_font(28)
    y = _draw_wrapped_text(
        draw, summary, pad, y,
        max_width=CARD_W - pad * 2,
        font=font_summary,
        fill=SUMMARY_COLOR,
        line_spacing=8,
        max_lines=8,
    )

    # source + branding at bottom
    font_small = _load_font(24)
    draw.text((pad, CARD_H - 60), source, font=font_small, fill=SOURCE_COLOR)
    draw.text((CARD_W - pad - 120, CARD_H - 60), "Briefly", font=font_small, fill=SOURCE_COLOR)

    canvas.save(str(out_path), "JPEG", quality=75, optimize=True)
    return str(out_path)
