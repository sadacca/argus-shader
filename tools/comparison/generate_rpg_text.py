"""T-011 — RPG-style dialogue/letter content for the baseline visual
comparison, requested directly rather than reusing T-009's existing
5x7-pixel-font positive set: that font only covers the 16 letters needed
for T-009's own WORDS list, not enough for a readable sentence. This
generates two native-resolution (SNES-class 256x224, matching T-009/T-010's
own W,H convention) scenes with a small TrueType font rendered at a tiny
point size — the same technique T-042's `generate_shapes.py` already used
for individual letterforms, applied here at in-game text scale instead of
supersampled ground-truth scale:

- `rpg_dialogue_box.png` — a bordered dialogue box with two lines of
  flavor text, the actual shape RPG dialogue/menu text takes (a contrasting
  box, not bare text on the game background).
- `rpg_letters.png` — a handful of individual glyphs at a larger native
  tile size, for close-up per-letter comparison.

Usage: python3 tools/comparison/generate_rpg_text.py [--out DIR]
"""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
W, H = 256, 224  # SNES-class canvas, matches tools/patterns/generate_text_sets.py

BG = (24, 32, 48)  # typical dark-blue RPG field background
BOX_BG = (16, 16, 24)
BOX_BORDER = (240, 240, 248)
TEXT_FG = (255, 255, 255)

DIALOGUE_LINES = [
    "THE OLD SAGE SPEAKS:",
    "A storm gathers past the",
    "ridge. Rest here tonight.",
]

LETTER_SAMPLE = "AaGgRrWw"


def make_dialogue_box() -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    # A few background "field" tiles so the box has something to contrast
    # against, same spirit as real RPG overworld/dialogue framing.
    for ty in range(0, H, 16):
        for tx in range(0, W, 16):
            shade = 6 if ((tx // 16 + ty // 16) % 2 == 0) else 0
            d.rectangle([tx, ty, tx + 15, ty + 15], fill=(BG[0] + shade, BG[1] + shade, BG[2] + shade))

    box = [8, H - 76, W - 9, H - 9]
    d.rectangle(box, fill=BOX_BG, outline=BOX_BORDER, width=2)

    font = ImageFont.truetype(FONT_PATH, size=12)
    y = box[1] + 8
    for line in DIALOGUE_LINES:
        d.text((box[0] + 10, y), line, fill=TEXT_FG, font=font)
        y += 16
    return img


def make_letters() -> Image.Image:
    img = Image.new("RGB", (W, H), (10, 10, 14))
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT_PATH, size=28)
    cell = W // 4
    for i, ch in enumerate(LETTER_SAMPLE):
        cx, cy = (i % 4) * cell, (i // 4) * (H // 2)
        bbox = d.textbbox((0, 0), ch, font=font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        d.text((cx + (cell - w) / 2 - bbox[0], cy + (H // 2 - h) / 2 - bbox[1]), ch,
               fill=(255, 255, 255), font=font)
    return img


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="corpus/synthetic/rpg_text", type=Path)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    make_dialogue_box().save(args.out / "rpg_dialogue_box.png")
    make_letters().save(args.out / "rpg_letters.png")
    print(f"wrote rpg_dialogue_box.png, rpg_letters.png under {args.out}")


if __name__ == "__main__":
    main()
