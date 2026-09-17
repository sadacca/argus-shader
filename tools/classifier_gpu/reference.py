"""T-015 — CPU prototype of the GPU-friendly unique-color-count replacement.

tools/classifier_spike/spike_report.md's "Finding to carry into T-015" flags
that literal unique-color counting (T-004's classify.py) isn't ALU-cheap on a
GPU (its O(k^2) pairwise-compare / np.unique formulation), and recommends
prototyping a bitmask/popcount proxy over quantized luma bins before
committing to it in the shader. This module does that: same statistics as
classify.py, but `unique_colors` is replaced by `luma_bin_popcount` (OR each
tap's quantized-luma bin into a bitmask, popcount it — this is the exact
operation `bitCount()` does in GLSL ES 3.00+), and re-runs the same T-004
corpus evaluation to confirm the classification boundary doesn't move before
this becomes the GLSL implementation in classify_debug.slang.
"""
import glob
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "classifier_spike"))
from classify import (  # noqa: E402
    luma,
    sliding_windows,
    REPO_ROOT,
    CORPUS,
    eval_dither_ramp as _unused_eval_dither_ramp,  # not reused directly (needs `classify` override)
)

# 32 bins is the practical ceiling for this proxy: it's the full width of a
# single GLSL `int` bitmask (`mask |= 1 << bin; bitCount(mask)`), so going
# wider would need a second mask word for no ALU cost saving at 32. It also
# turns out to matter empirically, not just theoretically: 8 bins (bin width
# 32) merges this project's own near-black glyph-outline/background pair
# (luma ~0 vs ~13, see the "outlined" text_positive corpus and the
# 2026-09-17 note below) into the same bin, causing false dither-positives
# on ~81% of outlined-glyph foreground pixels; 32 bins (bin width 8)
# resolves that pair and drops the false-positive rate to 0% on that same
# corpus, at identical ALU cost and with the T-004 dither-vs-gradient
# separation score unchanged (0.908/1.000 either way).
N_LUMA_BINS = 32
BIN_WIDTH = 256.0 / N_LUMA_BINS


def compute_stats(rgb: np.ndarray):
    L = luma(rgb.astype(np.float32))
    H, W = L.shape
    win = sliding_windows(L, 5).reshape(H, W, 25)

    mean = win.mean(axis=2)
    variance = win.var(axis=2)

    offs = np.array([[(-1) ** (dx + dy) for dx in range(-2, 3)] for dy in range(-2, 3)], dtype=np.float32).reshape(25)
    centered = win - mean[..., None]
    checker_raw = (centered * offs[None, None, :]).mean(axis=2)
    spread = np.abs(centered).mean(axis=2)
    # MIN_SPREAD guard (added 2026-09-17, see classify_debug.slang's header
    # comment for the full story): checker_raw/spread is a 0/0-like
    # indeterminate form on a genuinely flat window. This CPU
    # implementation's float32 arithmetic happens to cancel exactly for
    # identical-uint8-sourced taps (checker_raw==0.0 bit-for-bit), but a
    # GPU's different summation order doesn't hit that same exact
    # cancellation, so its ratio comes out noise-dominated instead of zero
    # — verified on real hardware paths, not hypothetical. 0.5 (luma units,
    # 0-255 scale) is ~1000x the observed noise floor and far below any
    # real dithered-pattern spread, so this doesn't change genuine
    # detections; it exists so the CPU reference matches what the shader
    # actually needs to do to be robust, not just what happens to work in
    # exact float32.
    MIN_SPREAD = 0.5
    has_signal = spread >= MIN_SPREAD
    checkerboard_autocorr = np.where(has_signal, np.abs(checker_raw) / np.maximum(spread, MIN_SPREAD), 0.0)

    # GPU-friendly proxy: which of N_LUMA_BINS luma bins does each tap fall
    # into (bitCount(mask) in GLSL); popcount of the union across the window
    # in place of exact distinct-RGB-value counting.
    tap_bin = np.clip((win / BIN_WIDTH).astype(np.int32), 0, N_LUMA_BINS - 1)  # (H,W,25)
    popcount = np.zeros((H, W), dtype=np.float32)
    for b in range(N_LUMA_BINS):
        popcount += np.any(tap_bin == b, axis=2)

    binw = (win >= mean[..., None]).reshape(H, W, 5, 5)
    center_is_fg = binw[:, :, 2, 2]
    row = binw[:, :, 2, :]
    col = binw[:, :, :, 2]

    def center_run_length(mask_1d: np.ndarray) -> np.ndarray:
        left = np.ones(mask_1d.shape[:2], dtype=np.int32)
        cur = np.ones(mask_1d.shape[:2], dtype=bool)
        for i in (1, 0):
            cur = cur & mask_1d[:, :, i]
            left += cur.astype(np.int32)
        right = np.ones(mask_1d.shape[:2], dtype=np.int32)
        cur = np.ones(mask_1d.shape[:2], dtype=bool)
        for i in (3, 4):
            cur = cur & mask_1d[:, :, i]
            right += cur.astype(np.int32)
        return left + right - 1

    row_run = center_run_length(row)
    col_run = center_run_length(col)
    stroke_width = np.minimum(row_run, col_run).astype(np.float32)
    stroke_width = np.where(center_is_fg, stroke_width, 99.0)

    return {
        "variance": variance,
        "checkerboard_autocorr": checkerboard_autocorr,
        "luma_bin_popcount": popcount,
        "stroke_width": stroke_width,
    }


THRESH = {
    "checkerboard_hi": 0.15,
    "popcount_dither_max": 2,
    "variance_flat_max": 20.0,
    "stroke_width_max": 2.0,
}


def classify(rgb: np.ndarray) -> np.ndarray:
    s = compute_stats(rgb)
    H, W = s["variance"].shape
    out = np.zeros((H, W), dtype=np.uint8)

    is_dither = (s["checkerboard_autocorr"] >= THRESH["checkerboard_hi"]) & (
        s["luma_bin_popcount"] <= THRESH["popcount_dither_max"]
    )
    is_stroke = (s["stroke_width"] <= THRESH["stroke_width_max"]) & (~is_dither)
    is_flat = (s["variance"] <= THRESH["variance_flat_max"]) & (~is_dither) & (~is_stroke)
    is_gradient = (~is_dither) & (~is_stroke) & (~is_flat)

    out[is_dither] = 1
    out[is_gradient] = 2
    out[is_stroke] = 3
    out[is_flat] = 0
    return out


# ---------------------------------------------------------------------------
# Same evaluation methodology as tools/classifier_spike/classify.py, against
# this module's classify() instead.
# ---------------------------------------------------------------------------
def eval_dither_ramp(path: str):
    from PIL import Image
    img = np.array(Image.open(path).convert("RGB"))
    h = img.shape[0]
    mask_path = path.replace(".png", "_mask.png")
    zone_mask = np.array(Image.open(mask_path).convert("L")) > 127
    pred = classify(img)
    top_zone = zone_mask[: h // 2, :]
    bottom_zone = zone_mask[h // 2 :, :]
    top_pred = pred[: h // 2, :][top_zone]
    bottom_pred = pred[h // 2 :, :][bottom_zone]
    top_acc = (top_pred == 1).mean() if top_pred.size else float("nan")
    bottom_acc = (bottom_pred == 2).mean() if bottom_pred.size else float("nan")
    return top_acc, bottom_acc


def eval_checkerboard_block(path: str):
    from PIL import Image
    img = np.array(Image.open(path).convert("RGB"))
    h, w = img.shape[:2]
    pred = classify(img)
    bh, bw = h // 2, w // 2
    oy, ox = (h - bh) // 2, (w - bw) // 2
    block = pred[oy : oy + bh, ox : ox + bw]
    bg_mask = np.ones((h, w), dtype=bool)
    bg_mask[oy : oy + bh, ox : ox + bw] = False
    block_acc = (block == 1).mean()
    bg_acc = (pred[bg_mask] == 0).mean()
    return block_acc, bg_acc


def eval_diagonal_sweep(path: str) -> float:
    from PIL import Image
    img = np.array(Image.open(path).convert("RGB"))
    pred = classify(img)
    return (pred != 1).mean()


def eval_text_positive(path: str) -> float:
    from PIL import Image
    img = np.array(Image.open(path).convert("RGB"))
    L = luma(img.astype(np.float32))
    fg_mask = L > (L.mean() + 20)
    if fg_mask.sum() == 0:
        return float("nan")
    pred = classify(img)
    return (pred[fg_mask] == 3).mean()


def eval_text_negative(path: str) -> float:
    from PIL import Image
    img = np.array(Image.open(path).convert("RGB"))
    L = luma(img.astype(np.float32))
    fg_mask = L > (L.mean() + 20)
    if fg_mask.sum() == 0:
        return 0.0
    pred = classify(img)
    return (pred[fg_mask] == 3).mean()


def main():
    results = {}

    dither_paths = sorted(
        p for p in glob.glob(os.path.join(CORPUS, "dither_ramp", "*.png")) if not p.endswith("_mask.png")
    )
    top_accs, bottom_accs = [], []
    for p in dither_paths:
        t, b = eval_dither_ramp(p)
        top_accs.append(t)
        bottom_accs.append(b)
    results["dither_ramp_top_as_b"] = float(np.mean(top_accs))
    results["dither_ramp_bottom_as_c"] = float(np.mean(bottom_accs))

    check_paths = sorted(glob.glob(os.path.join(CORPUS, "checkerboard_transparency", "*.png")))
    block_accs, bg_accs = [], []
    for p in check_paths:
        blk, bg = eval_checkerboard_block(p)
        block_accs.append(blk)
        bg_accs.append(bg)
    results["checkerboard_block_as_b"] = float(np.mean(block_accs))
    results["checkerboard_bg_as_a"] = float(np.mean(bg_accs))

    diag_paths = sorted(glob.glob(os.path.join(CORPUS, "diagonal_sweep", "*.png")))
    results["diagonal_sweep_not_misread_as_dither"] = float(np.mean([eval_diagonal_sweep(p) for p in diag_paths]))

    pos_paths = sorted(glob.glob(os.path.join(CORPUS, "text_positive", "*.png")))
    results["text_positive_recall_as_d"] = float(np.mean([eval_text_positive(p) for p in pos_paths]))

    neg_paths = sorted(glob.glob(os.path.join(CORPUS, "text_negative", "*.png")))
    results["text_negative_false_positive_rate"] = float(np.mean([eval_text_negative(p) for p in neg_paths]))

    dither_vs_gradient_separation = min(results["dither_ramp_top_as_b"], results["dither_ramp_bottom_as_c"])
    results["dither_vs_aa_gradient_separation_score"] = dither_vs_gradient_separation

    print("T-015 popcount-proxy re-evaluation (vs. T-004's exact-unique-count baseline)")
    print("=" * 70)
    for k, v in results.items():
        print(f"{k:45s} {v:.3f}")
    print("=" * 70)
    passed = dither_vs_gradient_separation >= 0.85
    print(f"PASS/FAIL (dither vs AA-gradient separation >= 0.85, same bar as T-004): {'PASS' if passed else 'FAIL'}")
    return results, passed


if __name__ == "__main__":
    _, ok = main()
    sys.exit(0 if ok else 1)
