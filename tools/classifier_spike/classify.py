#!/usr/bin/env python3
"""T-004 spike: offline feasibility test for the §6a.3 two-level classifier.

Decomposition under test (docs/requirements.md §6a.3, docs/review-notes.md B2):
  - 3x3 binary edge topology -> 256-entry LUT (edge geometry; correctness/
    invariants are T-014's job, not this spike's).
  - 5x5 wide-kernel scalar statistics computed in ALU, no table, no branching:
    local variance, checkerboard autocorrelation, stroke-width estimate,
    unique-color count. These select which of the FR2 four region classes a
    pixel belongs to:
      a) hard-edge / flat-color
      b) intentional dither / checkerboard pattern
      c) already-AA'd gradient
      d) thin high-contrast monochrome stroke (glyph)

This script is CPU/numpy, deliberately not a shader. Its job is only to
answer T-004's explicit pass/fail axis: can the wide-kernel scalar statistics
tell class (b) apart from class (c)? Everything here (thresholds, exact
statistic formulas) is expected groundwork for T-015/T-016, not final tuning.

Usage: python3 tools/classifier_spike/classify.py
"""
import glob
import os
import sys

import numpy as np
from PIL import Image

CLASSES = ["a_hard_edge_flat", "b_dither", "c_aa_gradient", "d_text_stroke"]

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CORPUS = os.path.join(REPO_ROOT, "corpus", "synthetic")


def luma(rgb: np.ndarray) -> np.ndarray:
    return rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114


def sliding_windows(arr: np.ndarray, k: int) -> np.ndarray:
    """Return a (H,W,k,k[,C]) view of k x k windows, edge-padded."""
    pad = k // 2
    if arr.ndim == 2:
        padded = np.pad(arr, pad, mode="edge")
    else:
        padded = np.pad(arr, ((pad, pad), (pad, pad), (0, 0)), mode="edge")
    return np.lib.stride_tricks.sliding_window_view(padded, (k, k) if arr.ndim == 2 else (k, k, arr.shape[-1]))


def compute_stats(rgb: np.ndarray):
    """Compute the four wide-kernel (5x5) scalar statistics per pixel.

    rgb: (H,W,3) uint8/float array. Returns dict of (H,W) float arrays.
    """
    L = luma(rgb.astype(np.float32))
    H, W = L.shape
    win = sliding_windows(L, 5)  # (H,W,5,5)
    win = win.reshape(H, W, 25)

    mean = win.mean(axis=2)
    variance = win.var(axis=2)

    # Checkerboard autocorrelation: projection of the window onto the
    # Nyquist-diagonal checkerboard basis (-1)^(dx+dy), normalized by the
    # window's own spread so it reads as a correlation in ~[0,1] regardless
    # of local contrast. High => strong 1px-period alternation (ordered
    # dither); low => smooth local variation (AA gradient) even at equal
    # variance.
    offs = np.array([[(-1) ** (dx + dy) for dx in range(-2, 3)] for dy in range(-2, 3)], dtype=np.float32).reshape(25)
    centered = win - mean[..., None]
    checker_raw = (centered * offs[None, None, :]).mean(axis=2)
    spread = np.abs(centered).mean(axis=2) + 1e-6
    checkerboard_autocorr = np.abs(checker_raw) / spread

    # Unique-color count: quantize RGB to 4 bits/channel, count distinct
    # values in the 5x5 window.
    q = (rgb.astype(np.int32) >> 4)  # 0..15 per channel
    qkey = (q[..., 0] << 8) | (q[..., 1] << 4) | q[..., 2]
    qwin = sliding_windows(qkey.astype(np.int32), 5).reshape(H, W, 25)
    unique_colors = np.array([[len(np.unique(qwin[y, x])) for x in range(W)] for y in range(H)], dtype=np.float32)

    # Stroke-width estimate: threshold the window at its own mean, then take
    # the run length of the center row/col through the center pixel,
    # whichever is shorter, as a proxy for local stroke thickness. Only
    # meaningful where the center pixel itself is on the "foreground" side
    # of the threshold; elsewhere reported as a large sentinel (not a stroke).
    binw = (win >= mean[..., None]).reshape(H, W, 5, 5)
    center_is_fg = binw[:, :, 2, 2]
    row = binw[:, :, 2, :]  # center row, 5 wide
    col = binw[:, :, :, 2]  # center col, 5 tall

    def center_run_length(mask_1d: np.ndarray) -> np.ndarray:
        # mask_1d: (H,W,5) boolean, center index 2. Count contiguous True run
        # through index 2.
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
        return left + right - 1  # center counted once

    row_run = center_run_length(row)
    col_run = center_run_length(col)
    stroke_width = np.minimum(row_run, col_run).astype(np.float32)
    stroke_width = np.where(center_is_fg, stroke_width, 99.0)

    return {
        "variance": variance,
        "checkerboard_autocorr": checkerboard_autocorr,
        "unique_colors": unique_colors,
        "stroke_width": stroke_width,
    }


# Thresholds picked empirically against the T-008/T-009/T-010 corpus (see
# tune_thresholds() below / spike_report.md). Documented per T-004's
# acceptance criterion "statistic set that achieves it documented".
THRESH = {
    "checkerboard_hi": 0.15,   # >= this: strong 1px alternation -> dither candidate
    "unique_colors_dither_max": 2,  # dither windows see at most the 2 dithered colors
    "variance_flat_max": 20.0,   # below this: essentially flat/hard-edge, not gradient
    "stroke_width_max": 2.0,     # <= this at a foreground pixel: glyph-stroke candidate
    "unique_colors_flat_max": 3,
}


def classify(rgb: np.ndarray) -> np.ndarray:
    s = compute_stats(rgb)
    H, W = s["variance"].shape
    out = np.zeros((H, W), dtype=np.uint8)  # default class 0 = a

    is_dither = (s["checkerboard_autocorr"] >= THRESH["checkerboard_hi"]) & (
        s["unique_colors"] <= THRESH["unique_colors_dither_max"]
    )
    is_stroke = (s["stroke_width"] <= THRESH["stroke_width_max"]) & (~is_dither)
    is_flat = (s["variance"] <= THRESH["variance_flat_max"]) & (~is_dither) & (~is_stroke)
    is_gradient = (~is_dither) & (~is_stroke) & (~is_flat)

    out[is_dither] = 1  # b
    out[is_gradient] = 2  # c
    out[is_stroke] = 3  # d
    out[is_flat] = 0  # a
    return out


# ---------------------------------------------------------------------------
# Evaluation against the labelled synthetic corpus.
# ---------------------------------------------------------------------------
def eval_dither_ramp(path: str):
    img = np.array(Image.open(path).convert("RGB"))
    h = img.shape[0]
    mask_path = path.replace(".png", "_mask.png")
    zone_mask = np.array(Image.open(mask_path).convert("L")) > 127
    pred = classify(img)
    top_zone = zone_mask[: h // 2, :]  # ground truth: b (dither), transition pixels only
    bottom_zone = zone_mask[h // 2 :, :]  # ground truth: c (AA gradient), transition pixels only
    top_pred = pred[: h // 2, :][top_zone]
    bottom_pred = pred[h // 2 :, :][bottom_zone]
    top_acc = (top_pred == 1).mean() if top_pred.size else float("nan")
    bottom_acc = (bottom_pred == 2).mean() if bottom_pred.size else float("nan")
    return top_acc, bottom_acc


def eval_checkerboard_block(path: str):
    img = np.array(Image.open(path).convert("RGB"))
    h, w = img.shape[:2]
    pred = classify(img)
    bh, bw = h // 2, w // 2
    oy, ox = (h - bh) // 2, (w - bw) // 2
    block = pred[oy : oy + bh, ox : ox + bw]
    bg_mask = np.ones((h, w), dtype=bool)
    bg_mask[oy : oy + bh, ox : ox + bw] = False
    block_acc = (block == 1).mean()  # ground truth: b
    bg_acc = (pred[bg_mask] == 0).mean()  # ground truth: a
    return block_acc, bg_acc


def eval_text_positive(path: str) -> float:
    img = np.array(Image.open(path).convert("RGB"))
    L = luma(img.astype(np.float32))
    fg_mask = L > (L.mean() + 20)  # glyph strokes are the bright pixels
    if fg_mask.sum() == 0:
        return float("nan")
    pred = classify(img)
    return (pred[fg_mask] == 3).mean()  # ground truth: d


def eval_text_negative(path: str) -> float:
    img = np.array(Image.open(path).convert("RGB"))
    L = luma(img.astype(np.float32))
    fg_mask = L > (L.mean() + 20)
    if fg_mask.sum() == 0:
        return 0.0
    pred = classify(img)
    return (pred[fg_mask] == 3).mean()  # false-positive rate: fraction misclassified as d


def eval_diagonal_sweep(path: str) -> float:
    img = np.array(Image.open(path).convert("RGB"))
    pred = classify(img)
    # No dithering anywhere in this pattern; ground truth is "not b". Report
    # the fraction correctly kept out of the dither class as a sanity check
    # that hard 2-color edges don't get misread as dither.
    return (pred != 1).mean()


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
    results["diagonal_sweep_not_misread_as_dither"] = float(
        np.mean([eval_diagonal_sweep(p) for p in diag_paths])
    )

    pos_paths = sorted(glob.glob(os.path.join(CORPUS, "text_positive", "*.png")))
    results["text_positive_recall_as_d"] = float(np.mean([eval_text_positive(p) for p in pos_paths]))

    neg_paths = sorted(glob.glob(os.path.join(CORPUS, "text_negative", "*.png")))
    fp_rates = [eval_text_negative(p) for p in neg_paths]
    results["text_negative_false_positive_rate"] = float(np.mean(fp_rates))

    # T-004's explicit pass/fail axis.
    dither_vs_gradient_separation = min(
        results["dither_ramp_top_as_b"], results["dither_ramp_bottom_as_c"]
    )
    results["dither_vs_aa_gradient_separation_score"] = dither_vs_gradient_separation

    print("T-004 classifier spike results")
    print("=" * 60)
    for k, v in results.items():
        print(f"{k:45s} {v:.3f}")

    passed = dither_vs_gradient_separation >= 0.85
    print("=" * 60)
    print(f"PASS/FAIL (dither vs AA-gradient separation >= 0.85): {'PASS' if passed else 'FAIL'}")

    return results, passed


if __name__ == "__main__":
    _, ok = main()
    sys.exit(0 if ok else 1)
