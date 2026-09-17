"""T-017 — CPU reference for the class-(d) text/glyph protection reconstruction rule.

Builds on tools/classifier_gpu/reference.py's classify()/compute_stats()
(T-015/T-016) the same way T-019's dither rule does — this ticket only adds
the reconstruction rule applied to whatever the classifier already calls
class (d) (thin high-contrast monochrome stroke).

The rule (docs/requirements.md FR2, docs/backlog.md T-017): class (d) must
route to a "minimal-interpolation/nearest-preserving" reconstruction rather
than diagonal reconstruction, because font stroke widths (1-2 source pixels)
don't carry enough neighborhood context for edge-reconstruction algorithms to
classify correctly. Concretely: for class-(d) pixels, output the exact
source color (no interpolation at all). This is a strict subset of T-019's
rule with the blend amount pinned at 0 — no strength dial, no hardness
modulation, because FR2's requirement here isn't "prefer preserving, tunably"
the way dithering is; it's "never let this touch anything that isn't literal
nearest-sampling."

`reconstruct_protected()` implements that. `reconstruct_unprotected()` is a
comparison baseline representing what T-017 exists to *prevent*: every pixel
(including real glyph strokes) going through the same local-mean smoothing a
generic diagonal-reconstruction pass would apply, with no per-class routing
at all. This isn't a strawman - it's literally "class (d) doesn't exist as a
special case," which is the pre-T-017 state of this project. Comparing
against it is what makes the "protection actually helps" claim measurable
instead of asserted.

See report.md for the honest, measured result on the false-positive axis:
the current four wide-kernel statistics (T-015) cannot cleanly separate
glyph strokes from fur/architecture/weapon-outline art sharing the same
thin-stroke signature — this was flagged as a risk at T-004/T-010 time and
is confirmed here with the actual numbers, not newly introduced by this
ticket's reconstruction rule.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "classifier_gpu"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "classifier_spike"))
import reference as classifier_ref  # noqa: E402
from classify import sliding_windows, luma  # noqa: E402


def classify_masks(rgb: np.ndarray):
    """Returns (is_dither, is_stroke, is_flat) boolean masks, same decision
    logic as classifier_ref.classify() but split out so the reconstruction
    rule can key off is_stroke specifically."""
    s = classifier_ref.compute_stats(rgb)
    t = classifier_ref.THRESH
    is_dither = (s["checkerboard_autocorr"] >= t["checkerboard_hi"]) & (s["luma_bin_popcount"] <= t["popcount_dither_max"])
    is_stroke = (s["stroke_width"] <= t["stroke_width_max"]) & (~is_dither)
    is_flat = (s["variance"] <= t["variance_flat_max"]) & (~is_dither) & (~is_stroke)
    return is_dither, is_stroke, is_flat


def _local_mean(rgb: np.ndarray) -> np.ndarray:
    H, W = rgb.shape[:2]
    win = sliding_windows(rgb.astype(np.float32), 5).reshape(H, W, 25, 3)
    return win.mean(axis=2)


def reconstruct_protected(rgb: np.ndarray) -> np.ndarray:
    """T-017's rule: class (d) is exact source color; everything else falls
    back to the same local-mean placeholder T-019's debug shader uses for
    non-dither pixels (not this ticket's job to build a/c's real
    reconstruction — see report.md)."""
    _, is_stroke, _ = classify_masks(rgb)
    rgb_f = rgb.astype(np.float64)
    mean_color = _local_mean(rgb)
    return np.where(is_stroke[..., None], rgb_f, mean_color)


def reconstruct_unprotected(rgb: np.ndarray) -> np.ndarray:
    """Comparison baseline: no class-(d) special case at all."""
    return _local_mean(rgb)


def legibility_score(source: np.ndarray, reconstructed: np.ndarray, fg_mask: np.ndarray, thresh: float = 15.0) -> float:
    """Fraction of foreground (glyph-candidate) pixels whose reconstructed
    luma stays within `thresh` of the source luma — i.e., still reads as
    foreground rather than being washed toward the local background/blur
    average. Same "recall against ground truth" spirit as T-009's rubric
    (classify.py::eval_text_positive), applied to reconstruction fidelity
    instead of classification.
    """
    if fg_mask.sum() == 0:
        return float("nan")
    src_l = luma(source.astype(np.float64))
    rec_l = luma(reconstructed)
    return float((np.abs(rec_l - src_l) <= thresh)[fg_mask].mean())
