#!/usr/bin/env python3
"""T-014 — generate and bake the 256-entry 3x3 topology LUT.

Decomposition per docs/requirements.md §6a.3 / docs/review-notes.md B2: a 3x3
neighborhood gives 8 binary "differs from center" comparisons -> 2^8 = 256
entries, which is the genuinely LUT-sized part of the two-level classifier
(the wide 5x5/7x7 kernel is handled separately, in ALU, per T-015 — see
tools/classifier_spike/classify.py for that half's spike).

This is an original design, not derived from xBRZ/HQx source (docs/licensing.md
puts HQx-family LUT code in the clean-room-only bucket) — the *concept* of
"3x3 binary neighborhood -> LUT" is a generic, unpatentable idea common to
many pixel-art scalers, but the table contents here are computed from a
neighbor-angle vector-sum defined below, not read out of another project's
table.

Bit layout (index bit i, LSB = bit 0), 8 compass neighbors in clockwise order
starting at N, 45 degrees apart:

    bit 0 = N   (dx= 0, dy=-1)      7   0   1
    bit 1 = NE  (dx= 1, dy=-1)        \ | /
    bit 2 = E   (dx= 1, dy= 0)    6 -   *   - 2
    bit 3 = SE  (dx= 1, dy= 1)        / | \
    bit 4 = S   (dx= 0, dy= 1)      5   4   3
    bit 5 = SW  (dx=-1, dy= 1)
    bit 6 = W   (dx=-1, dy= 0)
    bit 7 = NW  (dx=-1, dy=-1)

A bit is 1 when that neighbor is classified as differing from the center
pixel (the caller does the actual luma/color threshold before indexing —
this table only maps the resulting 8-bit topology to edge geometry).

Per-entry payload (edge geometry, consumed by T-018's reconstruction):
  - edge_dir: unit vector = normalized sum of the unit vectors at each set
    bit's angle. This is the estimated local edge *tangent* direction (i.e.
    where color is roughly constant), used to orient sub-pixel reconstruction.
  - confidence: popcount(index) / 8, i.e. how many of the 8 neighbors differ.
    0 or 8 (all same / all different) means "no usable direction" — flagged
    separately since edge_dir is undefined (0-vector) in the all-same case.

Baked format: 256x1 RGBA8 texture (also written as a flat binary for engines
that don't want to go through an image loader). Channel mapping:
  R = edge_dir.x, encoded 0..255 for -1.0..1.0  (round(x*127.5+127.5))
  G = edge_dir.y, encoded the same way
  B = confidence, 0..255 for 0.0..1.0  (round(popcount/8 * 255))
  A = 255 always (reserved / unused, kept to avoid a 3-channel texture format
      that most backends would pad to 4 bytes anyway — see docs/requirements.md
      FR8 on avoiding unnecessary alpha, which applies to *render targets*,
      not this small static asset)

No runtime dependency on this generator: the shader only ever does a direct
`texelFetch(LUT, ivec2(index, 0), 0)` — divergence-free, no branching on the
lookup itself (branching, if any, happens on the *decoded* confidence value
afterward, which is a data-dependent but not index-dependent branch).

Usage: python3 tools/lut/generate_lut.py [--out tools/lut]
"""
import argparse
import math
import struct

from PIL import Image

NEIGHBOR_ANGLES_DEG = [0, 45, 90, 135, 180, 225, 270, 315]  # bit 0..7, clockwise from N


def neighbor_unit_vector(bit: int):
    # Screen space: +x right, +y down. N (bit 0) points "up" => (0,-1).
    deg = NEIGHBOR_ANGLES_DEG[bit]
    rad = math.radians(deg)
    return (math.sin(rad), -math.cos(rad))


NEIGHBOR_VECS = [neighbor_unit_vector(b) for b in range(8)]


def popcount(n: int) -> int:
    return bin(n).count("1")


def edge_geometry(index: int):
    sx = sy = 0.0
    for bit in range(8):
        if index & (1 << bit):
            vx, vy = NEIGHBOR_VECS[bit]
            sx += vx
            sy += vy
    mag = math.hypot(sx, sy)
    if mag > 1e-6:
        dirx, diry = sx / mag, sy / mag
    else:
        dirx, diry = 0.0, 0.0
    confidence = popcount(index) / 8.0
    return dirx, diry, confidence


def encode_channel(v_neg1_to_1: float) -> int:
    return max(0, min(255, round(v_neg1_to_1 * 127.5 + 127.5)))


def encode_confidence(v_0_to_1: float) -> int:
    return max(0, min(255, round(v_0_to_1 * 255.0)))


def build_table():
    entries = []
    for index in range(256):
        dx, dy, conf = edge_geometry(index)
        entries.append((encode_channel(dx), encode_channel(dy), encode_confidence(conf), 255))
    return entries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="tools/lut")
    args = ap.parse_args()

    entries = build_table()

    img = Image.new("RGBA", (256, 1))
    img.putdata(entries)
    png_path = f"{args.out}/topology_lut.png"
    img.save(png_path)
    print(f"wrote {png_path}")

    bin_path = f"{args.out}/topology_lut.bin"
    with open(bin_path, "wb") as f:
        for r, g, b, a in entries:
            f.write(struct.pack("BBBB", r, g, b, a))
    print(f"wrote {bin_path}")


if __name__ == "__main__":
    main()
