"""T-019 — CPU reference for the dither-preservation reconstruction rule.

Builds on tools/classifier_gpu/reference.py's classify()/compute_stats()
(T-015/T-016, already verified against the actual shader) rather than
re-deriving classification: T-019's job is only the *reconstruction* rule
applied to whatever compute_stats()+classify() already say is class (b)
(intentional dither/checkerboard).

The rule (docs/backlog.md T-019 acceptance criteria):
  1. Checkerboard-transparency (Genesis-style fake-alpha) must not be
     blurred to a flat color.
  2. Genesis-style manual dithering must be visibly preserved.
  3. Behavior must differ measurably between high-contrast ("NES-style
     hard") dither and low-contrast ("SNES-style", see
     generate_soft_dither.py) dither.

Design: each dither-classified pixel blends between its own exact source
value ("hardColor", full preservation) and its local 5x5-window mean color
("meanColor", what a naive smoothing/upscale pass would produce instead),
by a blend amount that depends on two things:

  - ARGUS_DITHER_STRENGTH (FR5 user parameter, default 1.0 = full
    preservation): at 1.0, blend amount is always 0 regardless of dither
    hardness — every dither pixel is fully preserved by default, matching
    this project's stated goal (docs/requirements.md's "Correctly preserve
    deliberate dithering... instead of destroying them as noise").
  - "hardness" = clamp(spread / SPREAD_HARD_REF, 0, 1), where `spread`
    (tools/classifier_gpu/reference.py's mean absolute luma deviation, the
    same statistic that already guards the checkerboard-autocorrelation
    0/0 case) stands in for how far apart the two dithered colors are.
    Even when the user turns preservation down, a genuinely stark
    high-contrast checkerboard degrades less than a soft one at the same
    strength setting: blending two very different colors into one average
    produces an obviously-wrong muddy color (a visible artifact, not just
    "less crisp"), whereas a soft, close-color dither degrades gracefully
    into ordinary smoothing — which is a reasonable trade against ALWAYS
    fully protecting every class-b pixel regardless of user intent.

    blend_amount = (1 - hardness) * (1 - ARGUS_DITHER_STRENGTH)

Non-dither pixels are passed through unchanged here — this ticket only
defines class (b)'s rule; classes (a)/(c)/(d) get their own reconstruction
in T-018/T-017/T-020, not stood up as a fake placeholder here.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "classifier_gpu"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "classifier_spike"))
import reference as classifier_ref  # noqa: E402
from classify import sliding_windows  # noqa: E402

SPREAD_HARD_REF = 20.0  # luma units; see report.md's corpus spread survey


def is_dither(stats: dict) -> np.ndarray:
    return (stats["checkerboard_autocorr"] >= classifier_ref.THRESH["checkerboard_hi"]) & (
        stats["luma_bin_popcount"] <= classifier_ref.THRESH["popcount_dither_max"]
    )


def reconstruct(rgb: np.ndarray, strength: float) -> np.ndarray:
    """rgb: (H,W,3) uint8. Returns (H,W,3) float64 in [0,255]."""
    rgb_f = rgb.astype(np.float64)
    stats = classifier_ref.compute_stats(rgb)
    dither_mask = is_dither(stats)

    H, W = rgb_f.shape[:2]
    win = sliding_windows(rgb_f.astype(np.float32), 5).reshape(H, W, 25, 3)
    mean_color = win.mean(axis=2)

    hardness = np.clip(stats["spread"] / SPREAD_HARD_REF, 0.0, 1.0)
    blend_amount = (1.0 - hardness) * (1.0 - strength)

    dithered_out = rgb_f * (1.0 - blend_amount[..., None]) + mean_color * blend_amount[..., None]
    return np.where(dither_mask[..., None], dithered_out, rgb_f)
