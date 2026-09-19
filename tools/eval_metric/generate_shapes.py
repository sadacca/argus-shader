"""T-042 — generate ground-truth reconstruction-accuracy test shapes.

Unlike this project's existing synthetic corpus (tools/patterns/, hand-drawn
directly at native low resolution) and T-018's own diagonal-sweep ground
truth (an analytic per-pixel formula, straight lines only), this generates
shapes at high supersampled resolution — where "correct" is just what a
raster library already drew, no closed-form formula needed — then
downsamples with a box filter to a native low resolution, simulating a
vector-quality source pixelized down to 8/16-bit console resolution. That
downsampled image is what gets handed to each candidate shader; the
original supersampled render is the ground truth run_eval.py compares
reconstructed output against. This generalizes past straight lines to any
shape a raster library can draw — a curve, real font letterforms, etc.

Usage: python3 tools/eval_metric/generate_shapes.py
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = Path(__file__).resolve().parent / "shapes"

SUPERSAMPLE = 8
NATIVE_SIZE = 48  # native (pixelized) resolution per shape tile, in px
HIGH_RES = NATIVE_SIZE * SUPERSAMPLE

BG = (24, 24, 24)
FG = (235, 235, 235)

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def make_diagonal_line(angle_deg: float = 30.0) -> Image.Image:
    img = Image.new("RGB", (HIGH_RES, HIGH_RES), BG)
    d = ImageDraw.Draw(img)
    import math
    cx, cy = HIGH_RES / 2, HIGH_RES / 2
    length = HIGH_RES * 0.8
    dx = math.cos(math.radians(angle_deg)) * length / 2
    dy = math.sin(math.radians(angle_deg)) * length / 2
    width = max(2, HIGH_RES // 24)
    d.line([(cx - dx, cy - dy), (cx + dx, cy + dy)], fill=FG, width=width)
    return img


def make_curve() -> Image.Image:
    img = Image.new("RGB", (HIGH_RES, HIGH_RES), BG)
    d = ImageDraw.Draw(img)
    pad = HIGH_RES // 6
    width = max(2, HIGH_RES // 24)
    d.arc([pad, pad, HIGH_RES - pad, HIGH_RES - pad], start=200, end=340, fill=FG, width=width)
    return img


def make_letter(ch: str) -> Image.Image:
    img = Image.new("RGB", (HIGH_RES, HIGH_RES), BG)
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT_PATH, size=int(HIGH_RES * 0.8))
    bbox = d.textbbox((0, 0), ch, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((HIGH_RES - w) / 2 - bbox[0], (HIGH_RES - h) / 2 - bbox[1]), ch, fill=FG, font=font)
    return img


SHAPES = {
    "diagonal_line_30deg": lambda: make_diagonal_line(30.0),
    "curve_arc": make_curve,
    "letter_A": lambda: make_letter("A"),
    "letter_g": lambda: make_letter("g"),
}


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, gen in SHAPES.items():
        high_res = gen()
        native = high_res.resize((NATIVE_SIZE, NATIVE_SIZE), Image.Resampling.BOX)

        high_res.save(OUT_DIR / f"{name}_groundtruth_{HIGH_RES}px.png")
        native.save(OUT_DIR / f"{name}_native_{NATIVE_SIZE}px.png")
        print(f"{name}: ground truth {HIGH_RES}x{HIGH_RES}, native (pixelized) {NATIVE_SIZE}x{NATIVE_SIZE}")

    print(f"\n{len(SHAPES)} shapes written under {OUT_DIR}")
    print(f"Upscale factor to compare against ground truth: {SUPERSAMPLE}x")


if __name__ == "__main__":
    sys.exit(main())
