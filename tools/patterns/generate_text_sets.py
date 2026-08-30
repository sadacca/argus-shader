#!/usr/bin/env python3
"""T-009 (positive) / T-010 (negative) text legibility test sets.

Both sets are synthetic/procedural so they are trivially redistributable (no
captured game frames, no third-party font files) per docs/requirements.md §8's
corpus-redistribution constraint.

T-009 — positive set: bitmap-style glyph sheets in 3 font styles (thin
sans-serif, outlined/drop-shadow, larger blocky), >=5 samples each. These are
what class (d) of FR2 is supposed to catch and protect.

T-010 — negative set, built alongside T-009 per docs/backlog.md ("must land
with T-009, not after"): non-text content sharing the same thin-high-contrast-
stroke signature that risks tripping the same heuristic — fur/hair line-art,
fine architectural detail, pixel-thin weapon outlines. >=15 samples across the
three categories.

Usage: python3 tools/patterns/generate_text_sets.py [--out corpus/synthetic]
"""
import argparse
import math
import os
import random

from PIL import Image

SEED = 20260830

# 5x7 pixel font, enough characters to build sample dialogue/menu/HUD strings.
FONT_5X7 = {
    "A": ["..#..", ".#.#.", "#...#", "#####", "#...#", "#...#", "#...#"],
    "E": ["#####", "#....", "####.", "#....", "#....", "#....", "#####"],
    "G": [".###.", "#....", "#....", "#.###", "#...#", "#...#", ".###."],
    "H": ["#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "I": ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "#####"],
    "L": ["#....", "#....", "#....", "#....", "#....", "#....", "#####"],
    "M": ["#...#", "##.##", "#.#.#", "#...#", "#...#", "#...#", "#...#"],
    "N": ["#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#", "#...#"],
    "O": [".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "P": ["####.", "#...#", "#...#", "####.", "#....", "#....", "#...."],
    "R": ["####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"],
    "S": [".####", "#....", "#....", ".###.", "....#", "....#", "####."],
    "T": ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."],
    "U": ["#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "V": ["#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."],
    "W": ["#...#", "#...#", "#...#", "#.#.#", "#.#.#", "##.##", "#...#"],
    " ": ["."] * 7,
}

WORDS = ["GAME", "OVER", "PRESS", "START", "LEVEL", "HP", "MP", "ITEM", "SAVE", "MENU"]


def rng_for(name: str) -> random.Random:
    return random.Random(f"{SEED}:{name}")


def glyph_mask(ch: str):
    rows = FONT_5X7.get(ch.upper(), FONT_5X7[" "])
    return rows


def draw_text(px, ox, oy, text, fg, scale=1, stroke="thin", outline=None):
    """stroke='thin' draws single-pixel glyph strokes as-is; 'blocky' doubles
    every set pixel to a 2x2 block for a heavier stroke weight. If outline is
    given, an outline color is drawn one pixel behind the glyph on all 4 sides
    (drop-shadow / outlined style)."""
    cx = ox
    for ch in text:
        rows = glyph_mask(ch)
        gw = len(rows[0])
        for gy, row in enumerate(rows):
            for gx, c in enumerate(row):
                if c != "#":
                    continue
                bw = 2 if stroke == "blocky" else 1
                x0 = cx + gx * scale
                y0 = oy + gy * scale
                if outline is not None:
                    for dx in (-1, 0, 1):
                        for dy in (-1, 0, 1):
                            if dx == 0 and dy == 0:
                                continue
                            _put_block(px, x0 + dx, y0 + dy, bw, outline)
                _put_block(px, x0, y0, bw, fg)
        cx += (gw + 1) * scale
    return cx


def _put_block(px, x, y, size, color):
    w, h = px.size
    for dy in range(size):
        for dx in range(size):
            xx, yy = x + dx, y + dy
            if 0 <= xx < w and 0 <= yy < h:
                px[xx, yy] = color


def make_glyph_sheet(w, h, style, rng):
    img = Image.new("RGB", (w, h), (12, 12, 20))
    px = img.load()
    px_size = SizedPixelAccess(img)
    fg = (255, 255, 255)
    outline = (0, 0, 0) if style == "outlined" else None
    stroke = "blocky" if style == "blocky" else "thin"
    y = 4
    line_h = 10 if style != "blocky" else 18
    while y + 8 < h:
        line = " ".join(rng.choice(WORDS) for _ in range(max(1, w // 60)))
        draw_text(px_size, 4, y, line, fg, stroke=stroke, outline=outline)
        y += line_h
    return img


class SizedPixelAccess:
    """Thin wrapper exposing .size alongside PIL's PixelAccess."""

    def __init__(self, img: Image.Image):
        self._img = img
        self._px = img.load()
        self.size = img.size

    def __setitem__(self, key, value):
        self._px[key] = value

    def __getitem__(self, key):
        return self._px[key]


POSITIVE_STYLES = {
    "thin_sans": {},
    "outlined": {},
    "blocky": {},
}

W, H = 256, 224  # SNES-class canvas, representative of dialogue/menu/HUD content


def build_positive_set(out_dir):
    for style in POSITIVE_STYLES:
        rng = rng_for(f"pos:{style}")
        for i in range(5):
            img = make_glyph_sheet(W, H, style, rng)
            path = os.path.join(out_dir, f"{style}_{i:02d}.png")
            img.save(path)
            print(f"wrote {path}")


# ---------------------------------------------------------------------------
# Negative set: content sharing the thin-high-contrast-stroke signature.
# ---------------------------------------------------------------------------
def make_fur(w, h, rng):
    img = Image.new("RGB", (w, h), (90, 70, 50))
    px = img.load()
    fg = (230, 210, 180)
    n_strokes = 40
    for _ in range(n_strokes):
        x0 = rng.uniform(0, w)
        y0 = rng.uniform(0, h)
        angle = rng.uniform(60, 120)  # near-vertical, irregular, like fur
        length = rng.uniform(6, 16)
        dx = math.cos(math.radians(angle))
        dy = math.sin(math.radians(angle))
        for t in range(int(length)):
            x, y = int(x0 + dx * t), int(y0 + dy * t)
            if 0 <= x < w and 0 <= y < h:
                px[x, y] = fg
    return img


def make_architecture(w, h, rng):
    img = Image.new("RGB", (w, h), (60, 60, 70))
    px = img.load()
    fg = (200, 200, 210)
    spacing = rng.choice([6, 8, 10])
    for x in range(0, w, spacing):
        for y in range(h):
            px[x, y] = fg
    for y in range(0, h, spacing):
        for x in range(w):
            px[x, y] = fg
    return img


def make_weapon_outline(w, h, rng):
    img = Image.new("RGB", (w, h), (20, 20, 24))
    px = img.load()
    fg = (240, 240, 200)
    # Simple sword silhouette: a straight blade line plus a crossguard, both
    # drawn as a single-pixel outline stroke — the exact signature FR2 class
    # (d) must not misclassify as a glyph.
    cx = w // 2
    top = int(h * 0.15)
    bottom = int(h * 0.75)
    for y in range(top, bottom):
        px[cx, y] = fg
        px[cx + 1, y] = fg
    guard_y = bottom - int(h * 0.08)
    for x in range(cx - 12, cx + 14):
        if 0 <= x < w:
            px[x, guard_y] = fg
    return img


NEGATIVE_MAKERS = {
    "fur_hair": make_fur,
    "architecture": make_architecture,
    "weapon_outline": make_weapon_outline,
}


def build_negative_set(out_dir):
    for category, fn in NEGATIVE_MAKERS.items():
        rng = rng_for(f"neg:{category}")
        for i in range(5):
            img = fn(W, H, rng)
            path = os.path.join(out_dir, f"{category}_{i:02d}.png")
            img.save(path)
            print(f"wrote {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="corpus/synthetic")
    args = ap.parse_args()

    pos_dir = os.path.join(args.out, "text_positive")
    neg_dir = os.path.join(args.out, "text_negative")
    os.makedirs(pos_dir, exist_ok=True)
    os.makedirs(neg_dir, exist_ok=True)

    build_positive_set(pos_dir)
    build_negative_set(neg_dir)


if __name__ == "__main__":
    main()
