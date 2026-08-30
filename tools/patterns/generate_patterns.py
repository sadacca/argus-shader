#!/usr/bin/env python3
"""T-008 synthetic test pattern generator.

Generates four pattern families, each isolating exactly one failure mode named in
docs/requirements.md §8, at each target system's native resolution and pixel aspect
ratio (docs/backlog.md T-008). Deterministic: a fixed seed drives every randomized
element so re-running regenerates byte-identical output.

Usage: python3 tools/patterns/generate_patterns.py [--out corpus/synthetic]
"""
import argparse
import os
import random

from PIL import Image

# System native resolution and pixel aspect ratio (PAR = display_w / render_w scaling
# already folded in as a single float multiplier applied to X only; square-pixel systems
# use 1.0). Values per docs/requirements.md FR7 systems list.
SYSTEMS = {
    "nes":     {"res": (256, 240), "par": 8.0 / 7.0},
    "smw":     {"res": (256, 224), "par": 8.0 / 7.0},   # SNES
    "genesis": {"res": (320, 224), "par": 32.0 / 35.0},
    "gb":      {"res": (160, 144), "par": 1.0},
    "gba":     {"res": (240, 160), "par": 1.0},
}

SEED = 20260830  # date of docs/requirements.md v0.2, kept fixed for reproducibility


def rng_for(name: str) -> random.Random:
    return random.Random(f"{SEED}:{name}")


# ---------------------------------------------------------------------------
# Pattern 1: dither ramp — isolates class (b) intentional dither vs class (c)
# already-AA'd gradient. Two sub-panels per image: top half is an ordered
# (Bayer-style) dither ramp between two flat colors (hard, no intermediate
# palette entries — Genesis/NES manual-dither convention); bottom half is a
# true smooth gradient using intermediate colors (what an AA'd source would
# look like). A classifier that can't tell these apart fails FR2's core bet.
# ---------------------------------------------------------------------------
BAYER_4X4 = [
    [0, 8, 2, 10],
    [12, 4, 14, 6],
    [3, 11, 1, 9],
    [15, 7, 13, 5],
]


def make_dither_ramp(w: int, h: int) -> Image.Image:
    """Top half: several hard 2-color edges, each dithered across a narrow
    (4px) transition zone via ordered (Bayer) dithering — no intermediate
    palette entries, matching the Genesis/NES manual-dither convention.
    Bottom half: the *same* edge positions, but transitioned with true
    intermediate colors (linear blend) over the same zone width, matching
    what an already-AA'd source edge looks like.

    Using many *local* short transitions (rather than one slow whole-image
    ramp) matters: a slow global gradient is locally near-flat within a 5x5
    window and isn't actually confusable with dither. Real AA-vs-dither
    ambiguity happens right at an edge, over a few pixels — this pattern
    reproduces that regime so it's a meaningful test of the two-level
    classifier's separation axis.
    """
    img = Image.new("RGB", (w, h))
    mask = Image.new("L", (w, h), 0)  # 255 = inside a transition zone (real ground truth)
    px = img.load()
    mpx = mask.load()
    color_a = (24, 32, 96)
    color_b = (220, 200, 64)
    half = h // 2
    zone = 4  # transition width in source pixels
    period = max(zone * 4, w // 8)
    edge_xs = list(range(period // 2, w, period))

    def nearest_edge_t(x: int):
        best = None
        for ex in edge_xs:
            t = (x - (ex - zone // 2)) / zone
            if 0.0 <= t < 1.0 and (best is None or abs(t - 0.5) < abs(best - 0.5)):
                best = t
        return best

    for y in range(h):
        for x in range(w):
            t = nearest_edge_t(x)
            if t is None:
                # Flat region between edges: pick whichever side we're on.
                left_edges = [ex for ex in edge_xs if ex <= x]
                on_b_side = len(left_edges) % 2 == 1
                px[x, y] = color_b if on_b_side else color_a
                continue
            mpx[x, y] = 255
            left_edges = [ex for ex in edge_xs if ex <= x]
            base_is_b = (len(left_edges) - 1) % 2 == 1 if left_edges else False
            lo, hi = (color_b, color_a) if base_is_b else (color_a, color_b)
            if y < half:
                threshold = (BAYER_4X4[y % 4][x % 4] + 0.5) / 16.0
                px[x, y] = lo if t < threshold else hi
            else:
                px[x, y] = tuple(int(a + (b - a) * t) for a, b in zip(lo, hi))
    img.dither_mask = mask  # stash for the caller (see save loop below)
    return img


# ---------------------------------------------------------------------------
# Pattern 2: diagonal sweep — isolates edge/curve reconstruction quality across
# a spread of angles. One straight two-color edge per tile, angle swept
# 15..75 degrees in 5-degree steps (13 tiles), tiled left-to-right.
# ---------------------------------------------------------------------------
def make_diagonal_sweep(w: int, h: int) -> Image.Image:
    import math

    angles = list(range(15, 76, 5))  # 15..75 step 5, inclusive -> 13 tiles
    tile_w = w // len(angles)
    img = Image.new("RGB", (w, h), (30, 30, 30))
    px = img.load()
    fg = (235, 235, 235)
    for i, deg in enumerate(angles):
        slope = math.tan(math.radians(deg))
        x0 = i * tile_w
        for ty in range(h):
            # Edge position within the tile shifts with y according to slope.
            edge_x = (h / 2 - ty) / slope if slope != 0 else 0
            split = tile_w / 2 + edge_x
            for tx in range(tile_w):
                x = x0 + tx
                if x >= w:
                    continue
                px[x, ty] = fg if tx >= split else (30, 30, 30)
    return img


# ---------------------------------------------------------------------------
# Pattern 3: glyph sheet — isolates class (d) thin monochrome strokes. A
# single representative bitmap glyph ('A') rendered at 1px stroke width,
# tiled across the frame. Fuller font-style coverage lives in T-009/T-010.
# ---------------------------------------------------------------------------
GLYPH_A = [
    "..#..",
    ".#.#.",
    "#...#",
    "#####",
    "#...#",
    "#...#",
    "#...#",
]


def make_glyph_sheet(w: int, h: int) -> Image.Image:
    img = Image.new("RGB", (w, h), (10, 10, 10))
    px = img.load()
    fg = (255, 255, 255)
    gw, gh = len(GLYPH_A[0]), len(GLYPH_A)
    pad = 2
    cols = w // (gw + pad)
    rows = h // (gh + pad)
    for r in range(rows):
        for c in range(cols):
            ox = c * (gw + pad) + pad
            oy = r * (gh + pad) + pad
            for gy, row in enumerate(GLYPH_A):
                for gx, ch in enumerate(row):
                    if ch == "#" and ox + gx < w and oy + gy < h:
                        px[ox + gx, oy + gy] = fg
    return img


# ---------------------------------------------------------------------------
# Pattern 4: checkerboard-transparency block — isolates the Genesis-style
# "fake alpha via 1px checkerboard of two opaque colors" technique that a
# naive smoothing pass destroys into a flat blended color.
# ---------------------------------------------------------------------------
def make_checkerboard_block(w: int, h: int) -> Image.Image:
    img = Image.new("RGB", (w, h), (40, 60, 40))
    px = img.load()
    color_a = (200, 40, 40)   # opaque sprite color
    color_b = (40, 60, 40)    # background color, matches bg so it reads as translucency
    # Central block uses 1px checkerboard of color_a / color_b to fake ~50% alpha.
    bw, bh = w // 2, h // 2
    ox, oy = (w - bw) // 2, (h - bh) // 2
    for y in range(oy, oy + bh):
        for x in range(ox, ox + bw):
            px[x, y] = color_a if (x + y) % 2 == 0 else color_b
    return img


PATTERNS = {
    "dither_ramp": make_dither_ramp,
    "diagonal_sweep": make_diagonal_sweep,
    "glyph_sheet": make_glyph_sheet,
    "checkerboard_transparency": make_checkerboard_block,
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="corpus/synthetic")
    args = ap.parse_args()

    for pattern_name, fn in PATTERNS.items():
        for system_name, spec in SYSTEMS.items():
            w, h = spec["res"]
            img = fn(w, h)
            out_dir = os.path.join(args.out, pattern_name)
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, f"{system_name}_{w}x{h}.png")
            img.save(out_path)
            print(f"wrote {out_path}")
            mask = getattr(img, "dither_mask", None)
            if mask is not None:
                mask_path = os.path.join(out_dir, f"{system_name}_{w}x{h}_mask.png")
                mask.save(mask_path)
                print(f"wrote {mask_path}")


if __name__ == "__main__":
    main()
