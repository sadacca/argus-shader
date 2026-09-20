"""F-1 (docs/backlog.md) — a numpy reference implementation of the
reconstruction model, scored directly by tools/gold_eval, with no shader
compile or GPU in the loop. No OpenGL/EGL import anywhere in this file or
its dependencies (generate_lut.py, scoring.py) — that's the point: every
prior algorithmic conclusion in this project was reached through a render
path that compiles GLSL -> SPIR-V -> GLES and stands up a fresh EGL context
per call (see render_pass.py), which is minutes per sweep. This is seconds.

`reconstruct()` is faithfully ported from the retired shipped shader
(shaders/shaders_slang/argus/experimental/shaders/mobile-lite.slang,
T-016/T-017/T-018/T-019's fused logic) — same classification thresholds,
same LUT, same blend math — specifically so it can be validated against
that shader's published gold_eval numbers
(validate_cpu_reference.py, ±0.5pp) before being trusted as the harness's
CPU-side ground truth. It is deliberately NOT the new F-2/F-3 algorithm:
F-1's job is to prove the fast path is faithful, not to be good. Once
validated, F-2 (continuous-orientation contour estimation) and F-3 (corner/
wedge model) replace the "edge reconstruction" section below — everything
above it (the 5x5 classification statistics) is expected to survive
largely intact, since diagnosis finding 2 (docs/backlog-status.md) is about
the reconstruction step, not the classifier.

Structural difference from the shader, NOT a behavioral one: the shader
recomputes its full 5x5/3x3 analysis per *output* pixel (diagnosis finding
1 — ~94% redundant at 4x scale) because sub-pixel position was never
separated from per-source-pixel classification. Every quantity below except
the final sub-pixel blend depends only on the integer source pixel, so this
port computes classification once per native pixel and evaluates the blend
per output pixel via nearest-neighbour upsampling of the per-native-pixel
fields — this produces bit-for-bit the same result as a naive per-output-
pixel port (both are evaluating the same formula, just with the
pixel-independent part factored out once) while incidentally being the
same restructuring P-1 asks for in the real shader.
"""
import re
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools" / "lut"))
from generate_lut import edge_geometry  # noqa: E402

RETIRED_SHADER = (
    REPO_ROOT / "shaders" / "shaders_slang" / "argus" / "experimental" / "shaders" / "mobile-lite.slang"
)

# --- classification thresholds, copied verbatim from mobile-lite.slang ---
CHECKERBOARD_HI = 0.15
POPCOUNT_DITHER_MAX = 2.0
VARIANCE_FLAT_MAX = 20.0
STROKE_WIDTH_MAX = 2.0
MIN_SPREAD = 0.5
SPREAD_HARD_REF = 20.0

# 5x5 tap order: dy outer (-2..2), dx inner (-2..2) — idx = (dy+2)*5+(dx+2).
# Matches the shader's nested loop exactly; every index below (11/10/13/14
# for the horizontal run, 7/2/17/22 for the vertical run, 12 for center) is
# meaningless unless this ordering is preserved.
_TAP_OFFSETS = [(dx, dy) for dy in range(-2, 3) for dx in range(-2, 3)]
SIGN = np.array([1.0, -1.0] * 12 + [1.0])  # 25 entries, matches shader literal exactly

# 8-direction topology-index bit order: N, NE, E, SE, S, SW, W, NW clockwise
# (tools/lut/generate_lut.py's own bit layout). Each maps to one of the 25
# taps already computed above, so no extra sampling is needed.
_OFFS = [(0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)]
_OFFS_TAP_IDX = [_TAP_OFFSETS.index(o) for o in _OFFS]

_LUT_DIR = np.zeros((256, 2), dtype=np.float64)
_LUT_CONF = np.zeros((256,), dtype=np.float64)
for _i in range(256):
    _dx, _dy, _conf = edge_geometry(_i)
    _LUT_DIR[_i] = (_dx, _dy)
    _LUT_CONF[_i] = _conf

_PRAGMA_PARAMETER_RE = re.compile(r'#pragma\s+parameter\s+(\w+)\s+"[^"]*"\s+([+-]?[\d.eE+-]+)')


def parse_pragma_parameter_defaults(slang_path: Path = RETIRED_SHADER) -> dict:
    """Standalone re-implementation of render_pass.py's function of the same
    name — duplicated rather than imported so this module never pulls in
    render_pass's OpenGL dependency. Both read the same shader file, so
    there's nothing to keep in sync by hand; this reads the live source
    every call."""
    defaults = {}
    for match in _PRAGMA_PARAMETER_RE.finditer(slang_path.read_text()):
        name, default_str = match.groups()
        defaults[name] = float(default_str)
    return defaults


def _luma(rgb: np.ndarray) -> np.ndarray:
    """rgb in 0..255 float; returns luma in 0..255, matching the shader's
    luma() * 255.0 (the shader's rgb is 0..1 normalized texture data)."""
    return 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]


def reconstruct(native_rgb: np.ndarray, scale: int, params: dict = None) -> np.ndarray:
    """native_rgb: (H, W, 3) uint8/float array. scale: integer upscale
    factor (gold_eval always calls with SUPERSAMPLE, an integer). Returns
    (H*scale, W*scale, 3) uint8, matching the shape/dtype convention every
    other gold_eval candidate returns."""
    if params is None:
        params = parse_pragma_parameter_defaults()
    edge_threshold = params.get("ARGUS_EDGE_THRESHOLD", 0.10)
    dither_strength = params.get("ARGUS_DITHER_STRENGTH", 1.0)

    img = native_rgb.astype(np.float64)
    H, W = img.shape[:2]
    S = int(scale)

    padded = np.pad(img, ((2, 2), (2, 2), (0, 0)), mode="edge")
    taps = np.stack(
        [padded[2 + dy:2 + dy + H, 2 + dx:2 + dx + W, :] for dx, dy in _TAP_OFFSETS], axis=0
    )  # (25, H, W, 3)
    L = _luma(taps)  # (25, H, W)

    mean = L.mean(axis=0)
    mean_color = taps.mean(axis=0)  # (H, W, 3)
    variance = ((L - mean) ** 2).mean(axis=0)

    dev = L - mean
    checker_raw = (dev * SIGN[:, None, None]).mean(axis=0)
    spread = np.abs(dev).mean(axis=0)
    has_signal = (spread >= MIN_SPREAD).astype(np.float64)
    checkerboard_autocorr = has_signal * np.abs(checker_raw) / np.maximum(spread, MIN_SPREAD)

    bin_idx = np.clip((L / 8.0).astype(np.int64), 0, 31)  # BIN_WIDTH = 256/32 = 8.0
    mask = np.zeros((H, W), dtype=np.int64)
    for i in range(25):
        np.bitwise_or(mask, (1 << bin_idx[i]), out=mask)
    luma_bin_popcount = np.array([bin(m).count("1") for m in mask.ravel()], dtype=np.float64).reshape(H, W)

    fg = L >= mean  # (25, H, W) bool
    center_fg = fg[12]

    def run(near, far, cur0):
        cur = cur0.copy()
        total = 1.0 + cur.astype(np.float64)
        cur &= far
        total += cur.astype(np.float64)
        return total

    row_left = run(fg[11], fg[10], fg[11])
    row_right = run(fg[13], fg[14], fg[13])
    row_run = row_left + row_right - 1.0
    col_left = run(fg[7], fg[2], fg[7])
    col_right = run(fg[17], fg[22], fg[17])
    col_run = col_left + col_right - 1.0
    stroke_width = np.where(center_fg, np.minimum(row_run, col_run), 99.0)

    is_dither = (checkerboard_autocorr >= CHECKERBOARD_HI) & (luma_bin_popcount <= POPCOUNT_DITHER_MAX)
    is_stroke = (stroke_width <= STROKE_WIDTH_MAX) & ~is_dither
    is_flat = (variance <= VARIANCE_FLAT_MAX) & ~is_dither & ~is_stroke

    center_color = taps[12]  # (H, W, 3)
    center_luma = L[12]

    # --- dither branch (constant per native pixel) ---
    hardness = np.clip(spread / SPREAD_HARD_REF, 0.0, 1.0)
    blend_amount = (1.0 - hardness) * (1.0 - dither_strength)
    dither_out = center_color + (mean_color - center_color) * blend_amount[..., None]

    base_out = center_color.copy()
    base_out[is_dither] = dither_out[is_dither]
    # is_stroke and is_flat both leave base_out == center_color, matching
    # the shader's "outColor stays centerColor" default exactly.

    # --- edge branch: topology index from the same 25 taps (3x3 subset) ---
    thresh_luma = edge_threshold * 255.0
    topo_index = np.zeros((H, W), dtype=np.int64)
    for bit, tap_idx in enumerate(_OFFS_TAP_IDX):
        differs = np.abs(L[tap_idx] - center_luma) > thresh_luma
        topo_index |= differs.astype(np.int64) << bit

    dir_x = _LUT_DIR[topo_index, 0]
    dir_y = _LUT_DIR[topo_index, 1]
    confidence = _LUT_CONF[topo_index]

    normal_x, normal_y = -dir_y, dir_x
    off_x = np.clip(np.round(normal_x), -1, 1).astype(np.int64)
    off_y = np.clip(np.round(normal_y), -1, 1).astype(np.int64)

    rows, cols = np.indices((H, W))
    pos_r = np.clip(rows + off_y, 0, H - 1)
    pos_c = np.clip(cols + off_x, 0, W - 1)
    neg_r = np.clip(rows - off_y, 0, H - 1)
    neg_c = np.clip(cols - off_x, 0, W - 1)
    color_pos = img[pos_r, pos_c]
    color_neg = img[neg_r, neg_c]

    edge_active = (~is_dither) & (~is_stroke) & (~is_flat) & (confidence > 0) & ~((off_x == 0) & (off_y == 0))

    # --- upsample per-native-pixel fields to output resolution (nearest) ---
    def up(a):
        return np.repeat(np.repeat(a, S, axis=0), S, axis=1)

    base_out_up = up(base_out)
    center_color_up = up(center_color)
    color_pos_up = up(color_pos)
    color_neg_up = up(color_neg)
    normal_x_up = up(normal_x)
    normal_y_up = up(normal_y)
    edge_active_up = up(edge_active)

    # --- sub-pixel fractional offset, same for every native-pixel cell
    # (srcCoordF for output pixel k within a cell = (k+0.5)/S, so frac =
    # (k+0.5)/S - 0.5, independent of which cell — see module docstring). ---
    f = (np.arange(S) + 0.5) / S - 0.5
    frac_x_up = np.tile(f, (H * S, W))
    frac_y_up = np.repeat(np.tile(f, H), W * S).reshape(H * S, W * S)

    dist = frac_x_up * normal_x_up + frac_y_up * normal_y_up
    t_pos = np.clip(dist * 2.0, 0.0, 1.0)[..., None]
    t_neg = np.clip(-dist * 2.0, 0.0, 1.0)[..., None]
    blended = np.where(
        dist[..., None] > 0.0,
        center_color_up + (color_pos_up - center_color_up) * t_pos,
        center_color_up + (color_neg_up - center_color_up) * t_neg,
    )

    out = np.where(edge_active_up[..., None], blended, base_out_up)
    return np.clip(out, 0, 255).astype(np.uint8)
