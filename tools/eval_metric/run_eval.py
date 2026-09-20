"""T-042 — standardized reconstruction-accuracy eval: run every executable
baseline (nearest-neighbour, Omniscale, argus-mobile-lite — see
tools/comparison/report.md for why ScaleFX/xBRZ/SABR/HQx aren't included)
against each shape in tools/eval_metric/shapes/ (generate_shapes.py),
upscale back to the shape's original supersampled resolution, and score
against that resolution's known-correct ground truth with a single,
reproducible metric: IoU (intersection-over-union) of the foreground shape
mask, i.e. "% overlap" — plus plain binarized pixel accuracy as a more
intuitive secondary number. Both use the same fixed luma threshold derived
from generate_shapes.py's known BG/FG colors, applied identically to
ground truth and every candidate, so the comparison isn't tuned per-image.

Writes a labeled audit contact sheet per shape (ground truth + each
baseline, shader name and score burned into the image) plus report.md's
summary table.

Usage: python3 tools/eval_metric/run_eval.py
"""
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools" / "render_harness"))

from render_pass import render_pass, parse_pragma_parameter_defaults  # noqa: E402
from generate_shapes import SHAPES, SUPERSAMPLE, BG, FG  # noqa: E402

SHAPES_DIR = Path(__file__).resolve().parent / "shapes"
AUDIT_DIR = Path(__file__).resolve().parent / "audit"

MOBILE_LITE = REPO_ROOT / "shaders" / "shaders_slang" / "argus" / "experimental" / "shaders" / "mobile-lite.slang"
OMNISCALE = REPO_ROOT / "tools" / "edge_reconstruct" / "reference_shaders" / "omniscale.slang"

# Fixed threshold from generate_shapes.py's known BG=(24,24,24)/FG=(235,235,235)
# luma midpoint — not re-derived per image, so every baseline (including
# ground truth) is binarized identically.
LUMA = lambda rgb: 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
THRESHOLD = (LUMA(np.array([[BG]])) + LUMA(np.array([[FG]]))).item() / 2.0


def nearest_neighbour(native_img: Image.Image, scale: int) -> np.ndarray:
    return np.array(native_img.resize(
        (native_img.width * scale, native_img.height * scale), Image.Resampling.NEAREST
    ).convert("RGB"))


def score(reconstructed_rgb: np.ndarray, ground_truth_rgb: np.ndarray) -> tuple:
    recon_fg = LUMA(reconstructed_rgb.astype(np.float64)) > THRESHOLD
    gt_fg = LUMA(ground_truth_rgb.astype(np.float64)) > THRESHOLD
    intersection = np.logical_and(recon_fg, gt_fg).sum()
    union = np.logical_or(recon_fg, gt_fg).sum()
    iou = intersection / union if union > 0 else 1.0
    accuracy = (recon_fg == gt_fg).mean()
    return iou, accuracy


def label(img: Image.Image, text: str) -> Image.Image:
    """Burn a label bar into the bottom of `img` — this is the "audit"
    labeling: every saved image states which shader produced it and its
    score, so flipping through the audit/ directory doesn't require
    cross-referencing filenames against report.md."""
    bar_h = 28
    out = Image.new("RGB", (img.width, img.height + bar_h), (10, 10, 10))
    out.paste(img, (0, 0))
    d = ImageDraw.Draw(out)
    font = ImageFont.load_default()
    d.text((4, img.height + 6), text, fill=(255, 255, 255), font=font)
    return out


def contact_sheet(cells: list) -> Image.Image:
    """cells: list of (labeled_image) laid out in a single row."""
    w = sum(c.width for c in cells) + 8 * (len(cells) - 1)
    h = max(c.height for c in cells)
    sheet = Image.new("RGB", (w, h), (10, 10, 10))
    x = 0
    for c in cells:
        sheet.paste(c, (x, 0))
        x += c.width + 8
    return sheet


def main():
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    results = {}

    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        mobile_lite_params = parse_pragma_parameter_defaults(MOBILE_LITE)

        for shape_name in SHAPES:
            gt_path = next(SHAPES_DIR.glob(f"{shape_name}_groundtruth_*.png"))
            native_path = next(SHAPES_DIR.glob(f"{shape_name}_native_*.png"))
            gt_img = Image.open(gt_path).convert("RGB")
            gt_rgb = np.array(gt_img)
            native_img = Image.open(native_path).convert("RGB")

            cells = [label(gt_img, "ground truth (supersampled render)")]
            row_scores = {}

            candidates = [
                ("nearest-neighbour", None),
                ("omniscale", OMNISCALE),
                ("argus-mobile-lite", MOBILE_LITE),
            ]
            for cand_name, shader in candidates:
                if shader is None:
                    recon = nearest_neighbour(native_img, SUPERSAMPLE)
                else:
                    params = mobile_lite_params if shader is MOBILE_LITE else {}
                    recon = render_pass(shader, native_path, float(SUPERSAMPLE), tmpdir, params)[..., :3]

                iou, acc = score(recon, gt_rgb)
                row_scores[cand_name] = (iou, acc)
                cells.append(label(Image.fromarray(recon), f"{cand_name}: {iou*100:.1f}% overlap, {acc*100:.1f}% px acc"))

            contact_sheet(cells).save(AUDIT_DIR / f"{shape_name}.png")
            results[shape_name] = row_scores
            print(f"{shape_name}: " + "  ".join(f"{n}={iou*100:.1f}%" for n, (iou, acc) in row_scores.items()))

    write_report(results)
    print(f"\nAudit contact sheets written under {AUDIT_DIR}")


def write_report(results: dict):
    lines = [
        "# T-042 — standardized ground-truth overlap eval",
        "",
        "Generated by `generate_shapes.py` + `run_eval.py`. Method: each shape is drawn at "
        f"{SUPERSAMPLE}x supersampled resolution (the ground truth — no closed-form formula needed, "
        "just what the raster library already drew), box-downsampled to native resolution (the "
        "pixelized input every baseline actually receives), then each baseline upscales that native "
        f"image back to the original {SUPERSAMPLE}x scale. Both ground truth and every reconstruction "
        "are binarized with the same fixed luma threshold (derived from the shapes' own known "
        "background/foreground colors, not tuned per image), and scored as IoU "
        "(intersection-over-union) of the foreground shape mask — \"% overlap\" — plus plain "
        "binarized pixel accuracy as a more intuitive secondary number.",
        "",
        "Labeled audit contact sheets (ground truth + every baseline, shader name and score burned "
        "into each image) are under `audit/` — one PNG per shape, meant to be flipped through "
        "directly rather than cross-referenced against this table.",
        "",
        "## Result",
        "",
        "| shape | nearest-neighbour | omniscale | argus-mobile-lite |",
        "|---|---:|---:|---:|",
    ]
    for shape_name, row in results.items():
        cells = []
        for cand in ("nearest-neighbour", "omniscale", "argus-mobile-lite"):
            iou, acc = row[cand]
            cells.append(f"{iou*100:.1f}% ({acc*100:.1f}% px)")
        lines.append(f"| {shape_name} | " + " | ".join(cells) + " |")

    lines += [
        "",
        "(`% overlap (% px acc)` — IoU is the primary, standardized number; pixel accuracy is a "
        "secondary, more intuitive cross-check.)",
        "",
        "## Reading the result honestly",
        "",
        "This metric gives a more mixed picture than `tools/comparison/report.md`'s headline glyph "
        "win, and both should be read together rather than citing the favorable one alone: "
        "argus-mobile-lite loses to Omniscale on IoU for 3 of these 4 shapes (`diagonal_line_30deg`, "
        "`curve_arc`, `letter_A`) and only wins on `letter_g` — Omniscale's smoothing, which visibly "
        "rounds glyph corners and is why it loses badly on `tools/comparison`'s `glyph_sheet` test "
        "(a filled sans-serif glyph at native pixel-art scale, the shape T-017's protection rule is "
        "actually built to hold the line on), also gives it a small but consistent IoU edge on these "
        "thinner, smaller supersampled strokes and curves, where anti-aliased smoothing tends to "
        "overlap the ground truth mask slightly more than argus-mobile-lite's blockier, "
        "nearest-preserving-by-default reconstruction. This is the same shape of honest non-win as "
        "T-018's own Omniscale comparison (wins 1 of 5 tested scales) — a different, standardized "
        "metric corroborating a limitation already on record, not a new regression.",
        "",
        "## What this does and doesn't cover",
        "",
        "- Only the baselines `tools/comparison/` can actually execute (nearest-neighbour, "
        "Omniscale, argus-mobile-lite) are scored here — same ScaleFX (multi-pass infra gap) and "
        "xBRZ/SABR/HQx (licensing-scope call) limitations as `tools/comparison/report.md`, not "
        "re-derived.",
        "- Four shapes (one diagonal line, one curved arc, two letterforms), not an exhaustive sweep "
        "of angles/curves/glyphs — the pipeline (`generate_shapes.py`'s `SHAPES` dict) is built to "
        "make adding more a one-line change, not a new mechanism.",
        "- IoU on a single fixed threshold rewards getting the *shape boundary* right; it doesn't "
        "score color accuracy away from edges (a reconstruction that shifts interior color but keeps "
        "the boundary in the same place scores the same). That's a deliberate, stated scope, not an "
        "oversight — boundary placement is what this project's own reconstruction rules (T-018's "
        "edge-directed blend especially) are actually trying to get right.",
    ]
    (Path(__file__).resolve().parent / "report.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
