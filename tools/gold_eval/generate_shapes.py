"""Gold-standard hard-case eval corpus, built per direct user request after
real RetroArch screenshots showed argus-mobile-lite performing worse than
expected: the earlier T-042/T-011 synthetic content (a dialogue box, plain
letterforms) turned out to be dominated by near-axis-aligned edges that
mostly route through T-017's stroke-protect path, never really exercising
T-018's edge reconstruction — not representative of what actually breaks
pixel-art upscalers. This corpus targets the two classic hard cases
instead:

- **V** — a sharp, acute-angle corner. Smoothing algorithms characteristically
  round or bevel sharp vertices; nearest/pixel-exact reconstruction must
  hold the point exactly.
- **O** — a ring. Continuous curvature in every direction, no single
  dominant edge direction anywhere along it — the direct opposite case
  from a sharp corner, and the case T-018's own report already names as
  its weak point (the topology LUT's 8 discrete compass directions
  approximate a continuous curve imperfectly, "compass-snapping").

**Two ground-truth regimes, not one** — this is the actual methodology
fix, not just new shapes. T-042's own IoU metric mechanically rewards
smoothing (it scores against a smooth antialiased source), which biases
every comparison toward algorithms that blur — the opposite of what a
"preserve deliberate pixel art" design goal wants. Scoring against a
single ground truth regime can't separate "good at recovering a hidden
smooth source" from "good at leaving genuinely-blocky art alone", so this
generates both explicitly:

- `vector/` — the shape drawn at high supersampled resolution (a real
  smooth source exists), box-downsampled to native. Ground truth = the
  supersampled render. Tests: how well does each candidate recover the
  smooth edge a pixelized-down vector source implies?
- `8bit/` — the shape drawn directly at native resolution with hard,
  blocky placement (nearest-neighbour rasterization, no antialiasing,
  no hidden smooth source — this is what real hand-drawn retro pixel art
  actually is). Ground truth = a clean nearest-neighbour enlargement of
  that same native image. Tests: how well does each candidate leave
  intentionally-blocky art alone, rather than smoothing something that
  was never meant to be smooth?

Both regimes render at the same final resolution for direct comparability.

Usage: python3 tools/gold_eval/generate_shapes.py
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

OUT_DIR = Path(__file__).resolve().parent / "shapes"

SUPERSAMPLE = 8
NATIVE_SIZE = 48
HIGH_RES = NATIVE_SIZE * SUPERSAMPLE

BG = (24, 24, 24)
FG = (235, 235, 235)


def draw_v(d: ImageDraw.ImageDraw, size: int, stroke: int):
    """A sharp acute-angle chevron (~35 degrees at the vertex), like the
    letter V but drawn as a pure geometric corner, not a font glyph."""
    apex = (size * 0.5, size * 0.88)
    left = (size * 0.18, size * 0.10)
    right = (size * 0.62, size * 0.10)
    d.line([left, apex, right], fill=FG, width=stroke, joint="curve")
    # joint="curve" rounds the vertex in PIL — redraw a tiny fill at the
    # apex isn't needed since PIL's round join only softens by ~stroke/2,
    # and what we're measuring is exactly whether each *upscaler* preserves
    # or further rounds this corner, not PIL's own rasterization choice.


def draw_o(d: ImageDraw.ImageDraw, size: int, stroke: int):
    """A ring: continuous curvature at every point, inner and outer edge."""
    pad = size * 0.12
    d.ellipse([pad, pad, size - pad, size - pad], outline=FG, width=stroke)


SHAPES = {
    "v_corner": draw_v,
    "o_ring": draw_o,
}


def make_vector(name: str, draw_fn):
    img = Image.new("RGB", (HIGH_RES, HIGH_RES), BG)
    d = ImageDraw.Draw(img)
    draw_fn(d, HIGH_RES, max(2, HIGH_RES // 20))
    native = img.resize((NATIVE_SIZE, NATIVE_SIZE), Image.Resampling.BOX)
    return img, native


def make_8bit(name: str, draw_fn):
    """Draw directly at native resolution — hard block edges, no hidden
    smooth source. Ground truth is a plain nearest-neighbour enlargement
    of this same native image, computed by the eval script, not here."""
    img = Image.new("RGB", (NATIVE_SIZE, NATIVE_SIZE), BG)
    d = ImageDraw.Draw(img)
    draw_fn(d, NATIVE_SIZE, max(1, NATIVE_SIZE // 20))
    return img


def main():
    vector_dir = OUT_DIR / "vector"
    bit8_dir = OUT_DIR / "8bit"
    vector_dir.mkdir(parents=True, exist_ok=True)
    bit8_dir.mkdir(parents=True, exist_ok=True)

    for name, draw_fn in SHAPES.items():
        hi, native = make_vector(name, draw_fn)
        hi.save(vector_dir / f"{name}_groundtruth_{HIGH_RES}px.png")
        native.save(vector_dir / f"{name}_native_{NATIVE_SIZE}px.png")

        native_8bit = make_8bit(name, draw_fn)
        native_8bit.save(bit8_dir / f"{name}_native_{NATIVE_SIZE}px.png")

        print(f"{name}: vector regime ({HIGH_RES}x{HIGH_RES} + {NATIVE_SIZE}x{NATIVE_SIZE} native), "
              f"8bit regime ({NATIVE_SIZE}x{NATIVE_SIZE} native, blocky)")

    print(f"\n{len(SHAPES)} shapes x 2 regimes written under {OUT_DIR}")


if __name__ == "__main__":
    sys.exit(main())
