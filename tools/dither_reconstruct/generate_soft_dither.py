#!/usr/bin/env python3
"""T-019 test content — "SNES-style" soft ordered dithering.

tools/patterns/generate_patterns.py's dither_ramp/checkerboard_transparency
patterns already cover *hard* ordered dithering between two high-contrast
colors (the NES/Genesis convention: few palette entries, so the two dithered
colors are far apart in luma — measured spread ~17-76 luma units across the
existing corpus, see tools/dither_reconstruct/report.md). T-019's third
acceptance box explicitly wants dither-preservation behavior to differ
between that hard case and "SNES-style blending" dithering, but no existing
corpus content isolates the *soft* case: SNES's larger palette means when it
does still use ordered dithering (rather than real alpha blending, which
wouldn't be classified as dither at all — see report.md's note on that
distinction), the two dithered colors are much closer together.

This generator produces that missing case: the same Bayer-4x4 ordered
dither technique as generate_patterns.py's make_dither_ramp, but between two
colors ~20 luma units apart instead of ~85+ apart, at each system's native
resolution. This is new test content scoped to T-019, not a retroactive
change to T-008's corpus (which stays focused on the dither-vs-gradient
classification axis, not reconstruction).

Usage: python3 tools/dither_reconstruct/generate_soft_dither.py [--out corpus/synthetic/dither_soft]
"""
import argparse
import os

from PIL import Image

# Same system list/native resolutions as tools/patterns/generate_patterns.py.
SYSTEMS = {
    "nes": (256, 240),
    "smw": (256, 224),
    "genesis": (320, 224),
    "gb": (160, 144),
    "gba": (240, 160),
}

BAYER_4X4 = [
    [0, 8, 2, 10],
    [12, 4, 14, 6],
    [3, 11, 1, 9],
    [15, 7, 13, 5],
]

# ~20 luma units apart (0.299*dr + 0.587*dg + 0.114*db), close enough that a
# blended intermediate would still read as "a shade of the same color" rather
# than a jarring average — the SNES real-palette case. Contrast against
# checkerboard_transparency's (200,40,40)/(40,60,40) pair (~36 luma apart,
# but the flat non-dithered regions of that image contribute unrelated 0
# spread, so per-dither-pixel spread there measures ~17) and dither_ramp's
# (24,32,96)/(220,200,64) pair (~157 luma apart, spread ~45-76).
COLOR_A = (150, 140, 130)
COLOR_B = (170, 160, 110)


def make_soft_dither(w: int, h: int) -> Image.Image:
    img = Image.new("RGB", (w, h))
    px = img.load()
    period = 8  # checkerboard-transparency-style: one dithered region, not a ramp
    bw, bh = w // 2, h // 2
    ox, oy = (w - bw) // 2, (h - bh) // 2
    bg = tuple((a + b) // 2 for a, b in zip(COLOR_A, COLOR_B))
    for y in range(h):
        for x in range(w):
            if ox <= x < ox + bw and oy <= y < oy + bh:
                threshold = (BAYER_4X4[y % 4][x % 4] + 0.5) / 16.0
                px[x, y] = COLOR_A if threshold < 0.5 else COLOR_B
            else:
                px[x, y] = bg
    return img


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="corpus/synthetic/dither_soft")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    for name, (w, h) in SYSTEMS.items():
        img = make_soft_dither(w, h)
        path = os.path.join(args.out, f"{name}_{w}x{h}.png")
        img.save(path)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
