"""T-018 — CPU reference for LUT-topology-driven edge reconstruction
(classes a/c: hard-edge/flat and already-AA'd gradient).

Independently designed against the generic, published "3x3 binary
neighborhood -> edge geometry" idea `tools/lut/generate_lut.py` (T-014)
already documents as unpatentable and common to many pixel-art scalers
(docs/licensing.md §4) — not derived from reading any GPL/LGPL reference
implementation's source. Reuses `generate_lut.py`'s own `edge_geometry()`
function directly rather than re-deriving the LUT's math, so the two stay
in lockstep by construction instead of by hand-copied constants.

The rule:
  1. Build the 3x3 binary topology index the same way generate_lut.py's
     table is indexed: for each of the 8 compass neighbors, 1 if its luma
     differs from the center by more than ARGUS_EDGE_THRESHOLD (FR5,
     normalized 0..1 over the 0..255 luma range), 0 otherwise.
  2. Look up (edge_dir, confidence) for that index via generate_lut.py's
     edge_geometry() — edge_dir is the estimated local edge *tangent*
     (where color is roughly constant); confidence is popcount/8.
  3. normal = perpendicular(edge_dir) — the direction color actually
     *changes* across, i.e. the direction worth sub-pixel-blending along.
  4. confidence gates *whether* to blend at all (0 means no usable
     direction — e.g. a genuinely flat region, or a fully isolated single
     differing pixel — and is left untouched), but does not scale *how
     much*: confidence is popcount/8 (how many of the 8 neighbors differ),
     which measures how edge-like the local topology is, not how
     directionally certain its estimated tangent is. Scaling the blend
     amount by confidence was tried first and measurably hurt sub-pixel
     edge-position accuracy on the diagonal sweep (report.md Finding 2) —
     a confidently-classified edge with confidence well under 1.0 (common;
     e.g. a clean 45-degree staircase never reaches confidence 1.0) still
     deserves a full geometric blend along its estimated normal.
  5. For an output pixel at fractional sub-position `frac` within its
     source texel (frac in [-0.5, 0.5)^2, 0 = texel center): let
     signedDist = dot(frac, normal). At the texel center this is always 0,
     so the center pixel's own color is untouched regardless of confidence
     — this is what makes flat-color art a no-op. Moving toward a texel
     boundary along the normal blends smoothly toward whichever neighbor
     sits in that direction — this replaces the abrupt jump nearest-
     neighbour upscaling makes at every texel boundary with a smooth
     sub-pixel-accurate transition instead.

Classes (b)/(d) are not this ticket's job (T-019/T-017 already own them);
class (c) here just uses ordinary bilinear (4-tap) interpolation — a
gradient the source already anti-aliased doesn't need edge-directed
reconstruction, just needs to not be re-quantized back to blocky nearest-
neighbour steps.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "classifier_gpu"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "classifier_spike"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lut"))
import reference as classifier_ref  # noqa: E402
from classify import luma  # noqa: E402
from generate_lut import edge_geometry  # noqa: E402

ARGUS_EDGE_THRESHOLD = 0.10  # FR5 default (docs/backlog.md T-013)

# Precompute the 256-entry LUT once (dirx, diry, confidence), matching
# generate_lut.py's build_table() exactly (same function, unrounded floats
# instead of the baked 8-bit texture encoding, since the CPU reference
# should be checked against the shader's *decoded* values, not its own
# quantization — the shader itself samples the baked 8-bit texture and
# decodes it, so quantization error is expected and tolerated there).
_LUT = [edge_geometry(i) for i in range(256)]

# Neighbor bit offsets, same order/layout as generate_lut.py's header comment:
# bit 0=N(0,-1) 1=NE(1,-1) 2=E(1,0) 3=SE(1,1) 4=S(0,1) 5=SW(-1,1) 6=W(-1,0) 7=NW(-1,-1)
_NEIGHBOR_OFFSETS = [(0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)]


def _topology_index(L: np.ndarray, edge_threshold: float) -> np.ndarray:
    H, W = L.shape
    padded = np.pad(L, 1, mode="edge")
    center = padded[1:-1, 1:-1]
    idx = np.zeros((H, W), dtype=np.int32)
    thresh_luma = edge_threshold * 255.0
    for bit, (dx, dy) in enumerate(_NEIGHBOR_OFFSETS):
        neighbor = padded[1 + dy : 1 + dy + H, 1 + dx : 1 + dx + W]
        differs = np.abs(neighbor - center) > thresh_luma
        idx |= differs.astype(np.int32) << bit
    return idx


def reconstruct(rgb: np.ndarray, scale: float, edge_threshold: float = ARGUS_EDGE_THRESHOLD) -> np.ndarray:
    """rgb: (H,W,3) uint8 source. Returns (out_h,out_w,3) float64 in [0,255]."""
    H, W = rgb.shape[:2]
    rgb_f = rgb.astype(np.float64)
    L = luma(rgb_f.astype(np.float32))

    is_dither, is_stroke, is_flat = _classes(rgb)
    idx = _topology_index(L, edge_threshold)

    dirx = np.array([_LUT[i][0] for i in range(256)])[idx]
    diry = np.array([_LUT[i][1] for i in range(256)])[idx]
    conf = np.array([_LUT[i][2] for i in range(256)])[idx]
    normx, normy = -diry, dirx  # perpendicular(edge_dir)

    out_w, out_h = int(W * scale), int(H * scale)  # matches render_pass.py's truncation exactly
    out = np.zeros((out_h, out_w, 3), dtype=np.float64)

    for oy in range(out_h):
        sy = (oy + 0.5) / scale  # source-space continuous y
        cy = int(np.clip(np.floor(sy), 0, H - 1))
        fy = sy - (cy + 0.5)  # in [-0.5, 0.5)
        for ox in range(out_w):
            sx = (ox + 0.5) / scale
            cx = int(np.clip(np.floor(sx), 0, W - 1))
            fx = sx - (cx + 0.5)

            if is_dither[cy, cx] or is_stroke[cy, cx]:
                out[oy, ox] = rgb_f[cy, cx]
                continue

            if is_flat[cy, cx]:
                out[oy, ox] = rgb_f[cy, cx]
                continue

            c = conf[cy, cx]
            if c <= 0.0:
                out[oy, ox] = rgb_f[cy, cx]
                continue

            nx, ny = normx[cy, cx], normy[cy, cx]
            dist = fx * nx + fy * ny
            ox_off = int(np.clip(round(nx), -1, 1))
            oy_off = int(np.clip(round(ny), -1, 1))
            if ox_off == 0 and oy_off == 0:
                out[oy, ox] = rgb_f[cy, cx]
                continue
            pcx, pcy = int(np.clip(cx + ox_off, 0, W - 1)), int(np.clip(cy + oy_off, 0, H - 1))
            ncx, ncy = int(np.clip(cx - ox_off, 0, W - 1)), int(np.clip(cy - oy_off, 0, H - 1))
            # confidence (`c`) already gated whether to blend at all (the
            # `c <= 0.0` check above), not how much — see edge_debug.slang's
            # matching comment and report.md Finding 2 for why scaling the
            # blend amount by confidence was tried and measurably hurt
            # sub-pixel edge-position accuracy.
            center_color = rgb_f[cy, cx]
            if dist > 0:
                t = np.clip(dist * 2.0, 0.0, 1.0)
                out[oy, ox] = center_color * (1 - t) + rgb_f[pcy, pcx] * t
            else:
                t = np.clip(-dist * 2.0, 0.0, 1.0)
                out[oy, ox] = center_color * (1 - t) + rgb_f[ncy, ncx] * t
    return out


def _classes(rgb: np.ndarray):
    s = classifier_ref.compute_stats(rgb)
    t = classifier_ref.THRESH
    is_dither = (s["checkerboard_autocorr"] >= t["checkerboard_hi"]) & (s["luma_bin_popcount"] <= t["popcount_dither_max"])
    is_stroke = (s["stroke_width"] <= t["stroke_width_max"]) & (~is_dither)
    is_flat = (s["variance"] <= t["variance_flat_max"]) & (~is_dither) & (~is_stroke)
    return is_dither, is_stroke, is_flat
