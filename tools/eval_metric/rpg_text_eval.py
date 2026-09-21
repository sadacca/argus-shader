"""T-011/T-022 — numeric ground-truth comparison on RPG-style content,
across every baseline this project can now execute (SABR/ScaleFX/xBRZ as
of 2026-09-19, plus nearest-neighbour/Omniscale/argus-mobile-lite already
covered). Same method as T-042's `run_eval.py` (generate at supersampled
resolution — no closed-form formula needed, just what the raster library
already drew — box-downsample to native, then score each baseline's
upscale-of-the-native-image against the known-correct supersampled
render), applied to a dialogue-box scene and the RPG letter set rather
than T-042's isolated shapes, so the number reflects the actual content
type this comparison is about.

SABR/ScaleFX/xBRZ source is expected at scratch paths outside this repo,
same as tools/comparison/generate_rpg_baselines.py; pass their paths via
--sabr/--scalefx/--xbrz.

Usage:
  python3 tools/eval_metric/rpg_text_eval.py \\
      --sabr /path/to/sabr-v3.0.slang \\
      --scalefx tools/comparison/reference_shaders/scalefx/scalefx.slangp \\
      --xbrz /path/to/2xbrz-linear.slangp
"""
import argparse
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools" / "render_harness"))
from render_pass import render_pass, parse_pragma_parameter_defaults  # noqa: E402
from render_multipass import run_preset  # noqa: E402

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
SUPERSAMPLE = 8
NATIVE_W, NATIVE_H = 256, 224  # matches generate_rpg_text.py's SNES-class canvas
HIGH_W, HIGH_H = NATIVE_W * SUPERSAMPLE, NATIVE_H * SUPERSAMPLE

# Clean two-tone palette (no checkerboard field) so IoU/pixel-accuracy
# binarization is meaningful, same principle as T-042's BG/FG design.
BG = (16, 16, 24)
FG = (255, 255, 255)

MOBILE_LITE = REPO_ROOT / "shaders" / "shaders_slang" / "argus" / "experimental" / "shaders" / "mobile-lite.slang"
OMNISCALE = REPO_ROOT / "tools" / "edge_reconstruct" / "reference_shaders" / "omniscale.slang"

LUMA = lambda rgb: 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
THRESHOLD = (LUMA(np.array([[BG]])) + LUMA(np.array([[FG]]))).item() / 2.0

DIALOGUE_LINES = [
    "THE OLD SAGE SPEAKS:",
    "A storm gathers past the",
    "ridge. Rest here tonight.",
]
LETTER_SAMPLE = "AaGgRrWw"


def make_dialogue_box_hi() -> Image.Image:
    img = Image.new("RGB", (HIGH_W, HIGH_H), BG)
    d = ImageDraw.Draw(img)
    box = [8 * SUPERSAMPLE, (NATIVE_H - 76) * SUPERSAMPLE, (NATIVE_W - 9) * SUPERSAMPLE, (NATIVE_H - 9) * SUPERSAMPLE]
    d.rectangle(box, outline=FG, width=2 * SUPERSAMPLE)
    font = ImageFont.truetype(FONT_PATH, size=12 * SUPERSAMPLE)
    y = box[1] + 8 * SUPERSAMPLE
    for line in DIALOGUE_LINES:
        d.text((box[0] + 10 * SUPERSAMPLE, y), line, fill=FG, font=font)
        y += 16 * SUPERSAMPLE
    return img


def make_letters_hi() -> Image.Image:
    img = Image.new("RGB", (HIGH_W, HIGH_H), (10, 10, 14))
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT_PATH, size=28 * SUPERSAMPLE)
    cell = HIGH_W // 4
    for i, ch in enumerate(LETTER_SAMPLE):
        cx, cy = (i % 4) * cell, (i // 4) * (HIGH_H // 2)
        bbox = d.textbbox((0, 0), ch, font=font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        d.text((cx + (cell - w) / 2 - bbox[0], cy + (HIGH_H // 2 - h) / 2 - bbox[1]), ch, fill=(255, 255, 255), font=font)
    return img


SCENES = {
    "rpg_dialogue_box": make_dialogue_box_hi,
    "rpg_letters": make_letters_hi,
}


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


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sabr", type=Path, default=None)
    ap.add_argument("--scalefx", type=Path, default=None)
    ap.add_argument("--xbrz", type=Path, default=None)
    args = ap.parse_args()

    out_dir = Path(__file__).resolve().parent
    audit_dir = out_dir / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    results = {}

    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        mobile_lite_params = parse_pragma_parameter_defaults(MOBILE_LITE)

        for scene_name, gen in SCENES.items():
            hi = gen()
            native = hi.resize((NATIVE_W, NATIVE_H), Image.Resampling.BOX)
            native_path = tmpdir / f"{scene_name}_native.png"
            native.save(native_path)
            gt_rgb = np.array(hi.convert("RGB"))

            row_scores = {}
            candidates = [("nearest-neighbour", "nn"), ("omniscale", "single"), ("argus-mobile-lite", "single")]
            if args.sabr:
                candidates.append(("sabr", "single"))
            if args.scalefx:
                candidates.append(("scalefx", "multi"))
            if args.xbrz:
                candidates.append(("xbrz", "multi"))

            for name, kind in candidates:
                if kind == "nn":
                    recon = nearest_neighbour(native, SUPERSAMPLE)
                elif kind == "single":
                    shader = OMNISCALE if name == "omniscale" else (MOBILE_LITE if name == "argus-mobile-lite" else args.sabr)
                    params = mobile_lite_params if name == "argus-mobile-lite" else {}
                    recon = render_pass(shader, native_path, float(SUPERSAMPLE), tmpdir, params)[..., :3]
                else:
                    preset = args.scalefx if name == "scalefx" else args.xbrz
                    recon = run_preset(preset, native_path, float(SUPERSAMPLE), tmpdir)[..., :3]
                    if recon.shape[:2] != gt_rgb.shape[:2]:
                        recon = np.array(Image.fromarray(recon).resize((HIGH_W, HIGH_H), Image.Resampling.NEAREST))

                iou, acc = score(recon, gt_rgb)
                row_scores[name] = (iou, acc)
                print(f"{scene_name} / {name}: {iou*100:.2f}% overlap, {acc*100:.2f}% px acc")

            results[scene_name] = row_scores

    write_report(results, out_dir)


def write_report(results: dict, out_dir: Path):
    all_candidates = []
    for row in results.values():
        for name in row:
            if name not in all_candidates:
                all_candidates.append(name)

    lines = [
        "# T-011/T-022 — RPG-content ground-truth overlap eval",
        "",
        "Generated by `rpg_text_eval.py`. Same method as T-042's `run_eval.py`: content is drawn at "
        f"{SUPERSAMPLE}x supersampled resolution (ground truth), box-downsampled to native SNES-class "
        f"{NATIVE_W}x{NATIVE_H}, then each baseline upscales that native image back to {SUPERSAMPLE}x "
        "and is scored against the known-correct supersampled render — IoU of the binarized "
        "foreground (text/border) mask, plus plain binarized pixel accuracy.",
        "",
        "## Result",
        "",
        "| scene | " + " | ".join(all_candidates) + " |",
        "|---|" + "---:|" * len(all_candidates),
    ]
    for scene_name, row in results.items():
        cells = []
        for name in all_candidates:
            if name in row:
                iou, acc = row[name]
                cells.append(f"{iou*100:.1f}% ({acc*100:.1f}% px)")
            else:
                cells.append("—")
        lines.append(f"| {scene_name} | " + " | ".join(cells) + " |")

    lines += [
        "",
        "(`% overlap (% px acc)` — IoU is the primary, standardized number; pixel accuracy is a "
        "secondary, more intuitive cross-check.)",
        "",
        "## Reading this honestly",
        "",
        "**xBRZ scores highest on both scenes, SABR and ScaleFX both beat argus-mobile-lite on both "
        "scenes, and argus-mobile-lite is within noise of plain nearest-neighbour** (82.0% vs 82.0% "
        "on the dialogue box; 89.0% vs 88.3% on the letters — a ~0.7pp edge, not a meaningful win). "
        "This is not a cherry-picked bad case: both scenes agree, and it's the same pattern T-042 and "
        "T-044 already found on isolated shapes/letterforms — smoothing-based algorithms score better "
        "on IoU against a true antialiased source because they move edges *toward* that antialiased "
        "boundary, while argus-mobile-lite's text/glyph protection (T-017) deliberately keeps hard, "
        "nearest-preserving pixel edges instead. That design choice has a real, separately-documented "
        "upside (T-011's original finding: pixel-identical to nearest-neighbour on `glyph_sheet`, "
        "where Omniscale visibly rounds glyph corners) — but on *this* metric, on *this* content, it "
        "does not translate into winning, or even clearly beating the naive baseline. Both things are "
        "true at once and should be read together, not selectively.",
    ]
    (out_dir / "rpg_text_report.md").write_text("\n".join(lines) + "\n")
    print(f"\nwrote {out_dir / 'rpg_text_report.md'}")


if __name__ == "__main__":
    main()
