"""T-018 — verify edge_debug.slang against edge_reference.py, and check the
docs/backlog.md T-018 acceptance criteria directly against rendered output.

Usage: python3 tools/edge_reconstruct/verify_gpu.py
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools" / "render_harness"))
sys.path.insert(0, str(REPO_ROOT / "tools" / "edge_reconstruct"))

from render_pass import render_pass  # noqa: E402
import edge_reference as ref  # noqa: E402

SHADER = REPO_ROOT / "tools" / "edge_reconstruct" / "edge_debug.slang"
OMNISCALE = REPO_ROOT / "tools" / "edge_reconstruct" / "reference_shaders" / "omniscale.slang"

DIAGONAL_SWEEP = REPO_ROOT / "corpus/synthetic/diagonal_sweep/nes_256x240.png"
CHECKERBOARD = REPO_ROOT / "corpus/synthetic/checkerboard_transparency/genesis_320x224.png"

DIAG_ANGLES = list(range(15, 76, 5))  # matches tools/patterns/generate_patterns.py exactly


def render(shader: Path, image_path: Path, scale: float, tmpdir: Path) -> np.ndarray:
    return render_pass(shader, image_path, scale, tmpdir, {"ARGUS_EDGE_THRESHOLD": 0.10})[..., :3]


def check_tolerance(tmpdir: Path) -> bool:
    ok = True
    # edge_reference.reconstruct()'s per-pixel Python loop is slow; a small
    # crop is enough to check numeric parity (the math has no per-region
    # special-casing) without a multi-minute run.
    img = Image.open(DIAGONAL_SWEEP).convert("RGB")
    crop = img.crop((0, 100, 64, 140))
    crop_path = tmpdir / "diag_crop.png"
    crop.save(crop_path)
    crop_arr = np.array(crop)

    for scale in (1.0, 2.0):
        cpu = ref.reconstruct(crop_arr, scale)
        gpu = render(SHADER, crop_path, scale, tmpdir).astype(np.float64)
        err = np.abs(gpu - cpu)
        max_err = float(err.max())
        frac_over = float((err > 4.0).mean())
        status = "OK" if frac_over < 0.02 else "FAIL"
        if status == "FAIL":
            ok = False
        print(f"  [diag_crop scale={scale}] max_err={max_err:.2f} frac_over_tol={frac_over:.4f} {status}")
    return ok


def check_flat_art_no_regression(tmpdir: Path) -> bool:
    """No regression vs. nearest-neighbour on flat-color sprite art: the
    checkerboard-transparency image's flat background regions (everything
    outside the dithered block) should render byte-identical to a plain
    nearest-neighbour upscale, since confidence is 0 there (no topology
    edge) regardless of scale."""
    img = np.array(Image.open(CHECKERBOARD).convert("RGB"))
    h, w = img.shape[:2]
    bh, bw = h // 2, w // 2
    oy, ox = (h - bh) // 2, (w - bw) // 2
    flat_mask = np.ones((h, w), dtype=bool)
    flat_mask[oy : oy + bh, ox : ox + bw] = False  # exclude the dithered block itself

    scale = 3
    gpu = render(SHADER, CHECKERBOARD, float(scale), tmpdir)
    nn = np.repeat(np.repeat(img, scale, axis=0), scale, axis=1)
    flat_mask_up = np.repeat(np.repeat(flat_mask, scale, axis=0), scale, axis=1)

    diff = np.abs(gpu.astype(np.int32) - nn.astype(np.int32)).max(axis=2)
    max_diff = int(diff[flat_mask_up].max())
    print(f"  flat-region max |shader - nearest-neighbour| = {max_diff} (want 0)")
    ok = max_diff == 0
    print(f"  PASS/FAIL: {'PASS' if ok else 'FAIL'}")
    return ok


def analytic_edge_x(tile_w: int, h: int, deg: int, ty: int) -> float:
    import math
    slope = math.tan(math.radians(deg))
    edge_x = (h / 2 - ty) / slope if slope != 0 else 0
    return tile_w / 2 + edge_x


def find_subpixel_crossing(row: np.ndarray, threshold: float) -> float:
    """Sub-pixel x where `row` (luma-like, ascending dark->light) crosses
    `threshold`, via linear interpolation between the bracketing samples."""
    above = row >= threshold
    if not above.any() or above.all():
        return float("nan")
    idx = np.argmax(above)  # first index where row >= threshold
    if idx == 0:
        return 0.0
    y0, y1 = row[idx - 1], row[idx]
    if y1 == y0:
        return float(idx)
    frac = (threshold - y0) / (y1 - y0)
    return (idx - 1) + frac


def check_subpixel_accuracy(tmpdir: Path) -> bool:
    """Sub-pixel edge placement preserved: measure the reconstructed edge's
    sub-pixel crossing position per row against the diagonal_sweep pattern's
    own analytic edge position (tools/patterns/generate_patterns.py's own
    formula), and compare error against a plain nearest-neighbour upscale
    baseline."""
    scale = 4
    src = np.array(Image.open(DIAGONAL_SWEEP).convert("L"))
    h, w = src.shape
    tile_w = w // len(DIAG_ANGLES)
    threshold = (30 + 235) / 2.0

    gpu = render(SHADER, DIAGONAL_SWEEP, float(scale), tmpdir)
    gpu_l = np.array(Image.fromarray(gpu).convert("L"))
    nn = np.repeat(np.repeat(src, scale, axis=0), scale, axis=1)

    gpu_errs, nn_errs = [], []
    for i, deg in enumerate(DIAG_ANGLES):
        x0 = i * tile_w
        for ty in range(20, h - 20, 5):  # skip near tile edges/wraparound rows
            analytic = analytic_edge_x(tile_w, h, deg, ty) * scale
            oy = ty * scale + scale // 2
            row_gpu = gpu_l[oy, x0 * scale : (x0 + tile_w) * scale].astype(np.float64)
            row_nn = nn[oy, x0 * scale : (x0 + tile_w) * scale].astype(np.float64)
            gx = find_subpixel_crossing(row_gpu, threshold)
            nx = find_subpixel_crossing(row_nn, threshold)
            if np.isnan(gx) or np.isnan(nx):
                continue
            gpu_errs.append(abs(gx - analytic))
            nn_errs.append(abs(nx - analytic))

    gpu_mae = float(np.mean(gpu_errs))
    nn_mae = float(np.mean(nn_errs))
    print(f"  mean sub-pixel edge-position error (output px): edge_debug={gpu_mae:.3f}  nearest-neighbour={nn_mae:.3f}")
    ok = gpu_mae < nn_mae
    print(f"  PASS/FAIL (edge_debug more accurate than nearest-neighbour): {'PASS' if ok else 'FAIL'}")
    return ok


def check_beats_omniscale(tmpdir: Path) -> bool:
    """Comparison against Omniscale on the diagonal sweep: same sub-pixel
    edge-position error metric, applied identically to both renderers'
    actual output, at every scale RetroArch commonly runs a mobile-lite-
    class pass at (2x-6x) rather than one cherry-picked scale — an earlier
    single-scale check (4x only) happened to show a win that turned out not
    to generalize; see report.md Finding 2 for the full, honest breakdown
    and why this box is not being checked off in docs/backlog.md.

    SABR is deliberately not compared at all — see reference_shaders/
    NOTICE.md and report.md for why running it is a separate, still-open
    licensing-scope call this ticket doesn't make unilaterally.
    """
    src = np.array(Image.open(DIAGONAL_SWEEP).convert("L"))
    h, w = src.shape
    tile_w = w // len(DIAG_ANGLES)
    threshold = (30 + 235) / 2.0

    wins = 0
    per_scale = []
    for scale in (2, 3, 4, 5, 6):
        gpu = render(SHADER, DIAGONAL_SWEEP, float(scale), tmpdir)
        gpu_l = np.array(Image.fromarray(gpu).convert("L"))
        omni = render(OMNISCALE, DIAGONAL_SWEEP, float(scale), tmpdir)
        omni_l = np.array(Image.fromarray(omni).convert("L"))

        gpu_errs, omni_errs = [], []
        for i, deg in enumerate(DIAG_ANGLES):
            x0 = i * tile_w
            for ty in range(20, h - 20, 5):
                analytic = analytic_edge_x(tile_w, h, deg, ty) * scale
                oy = ty * scale + scale // 2
                row_gpu = gpu_l[oy, x0 * scale : (x0 + tile_w) * scale].astype(np.float64)
                row_omni = omni_l[oy, x0 * scale : (x0 + tile_w) * scale].astype(np.float64)
                gx = find_subpixel_crossing(row_gpu, threshold)
                ox = find_subpixel_crossing(row_omni, threshold)
                if np.isnan(gx) or np.isnan(ox):
                    continue
                gpu_errs.append(abs(gx - analytic))
                omni_errs.append(abs(ox - analytic))

        gpu_mae = float(np.mean(gpu_errs))
        omni_mae = float(np.mean(omni_errs))
        won = gpu_mae < omni_mae
        wins += int(won)
        per_scale.append((scale, gpu_mae, omni_mae, won))
        print(f"  scale={scale}: edge_debug={gpu_mae:.3f}  omniscale={omni_mae:.3f}  {'WIN' if won else 'LOSS'}")

    ok = wins == len(per_scale)
    print(f"  edge_debug wins {wins}/{len(per_scale)} tested scales.")
    print(f"  PASS/FAIL (beats Omniscale at every tested scale): {'PASS' if ok else 'FAIL'}")
    print("  Not gated into T-018's overall pass/fail below — see report.md Finding 2:"
          " a mixed, honestly-reported result, not a threshold this ticket can unilaterally redefine.")
    return ok


def main():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        print("=== Numeric parity: shader vs. edge_reference.py ===")
        tol_ok = check_tolerance(tmpdir)
        print()
        print("=== T-018 acceptance: no regression vs. nearest-neighbour on flat art ===")
        flat_ok = check_flat_art_no_regression(tmpdir)
        print()
        print("=== T-018 acceptance: sub-pixel edge placement preserved ===")
        subpixel_ok = check_subpixel_accuracy(tmpdir)
        print()
        print("=== Comparison vs. Omniscale on the diagonal sweep (informational, see report.md) ===")
        check_beats_omniscale(tmpdir)

    print()
    overall = tol_ok and flat_ok and subpixel_ok
    print(f"OVERALL (numeric parity + no-flat-regression + beats-nearest-neighbour): {'PASS' if overall else 'FAIL'}")
    print("(Omniscale comparison is informational, not gated -- see report.md Finding 2."
          " SABR comparison not run -- see reference_shaders/NOTICE.md.)")
    sys.exit(0 if overall else 1)


if __name__ == "__main__":
    main()
