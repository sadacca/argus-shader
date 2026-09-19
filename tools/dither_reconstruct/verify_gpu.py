"""T-019 — verify dither_debug.slang against reference.py, and check the
three acceptance criteria from docs/backlog.md directly against the actual
rendered shader output (not just the CPU model).

Usage: python3 tools/dither_reconstruct/verify_gpu.py
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools" / "render_harness"))
sys.path.insert(0, str(REPO_ROOT / "tools" / "classifier_gpu"))
sys.path.insert(0, str(REPO_ROOT / "tools" / "dither_reconstruct"))

from render_pass import render_pass  # noqa: E402
import dither_reference as recon_ref  # noqa: E402
import reference as classifier_ref  # noqa: E402 (classifier_gpu's reference.py)

SHADER = REPO_ROOT / "tools" / "dither_reconstruct" / "dither_debug.slang"

CHECKERBOARD = REPO_ROOT / "corpus/synthetic/checkerboard_transparency/genesis_320x224.png"
DITHER_RAMP = REPO_ROOT / "corpus/synthetic/dither_ramp/genesis_320x224.png"
DITHER_RAMP_MASK = REPO_ROOT / "corpus/synthetic/dither_ramp/genesis_320x224_mask.png"
SOFT_DITHER = REPO_ROOT / "corpus/synthetic/dither_soft/genesis_320x224.png"

STRENGTHS = [0.0, 0.5, 1.0]


def render(image_path: Path, strength: float, tmpdir: Path) -> np.ndarray:
    return render_pass(SHADER, image_path, 1.0, tmpdir, {"ARGUS_DITHER_STRENGTH": strength})[..., :3]


def check_tolerance(tmpdir: Path) -> bool:
    """Numeric parity between the shader and reference.py's reconstruct(),
    same tolerance-checking pattern as classifier_gpu/verify_gpu.py."""
    ok = True
    for path in (CHECKERBOARD, DITHER_RAMP, SOFT_DITHER):
        img = np.array(Image.open(path).convert("RGB"))
        for strength in STRENGTHS:
            cpu = recon_ref.reconstruct(img, strength)
            gpu = render(path, strength, tmpdir).astype(np.float64)
            err = np.abs(gpu - cpu)
            max_err = float(err.max())
            frac_over = float((err > 4.0).mean())  # 8-bit roundtrip tolerance
            status = "OK" if frac_over < 0.01 else "FAIL"
            if status == "FAIL":
                ok = False
            print(f"  [{path.name} strength={strength}] max_err={max_err:.2f} frac_over_tol={frac_over:.4f} {status}")
    return ok


def dither_region_mask(img: np.ndarray) -> np.ndarray:
    stats = classifier_ref.compute_stats(img)
    return recon_ref.is_dither(stats)


def mean_deviation_from_source(rendered: np.ndarray, source: np.ndarray, mask: np.ndarray) -> float:
    diff = np.abs(rendered.astype(np.float64) - source.astype(np.float64)).mean(axis=2)
    return float(diff[mask].mean()) if mask.any() else float("nan")


def check_acceptance_criteria(tmpdir: Path) -> bool:
    ok = True

    # 1. Checkerboard-transparency block survives without being blurred to
    # flat color, at the default strength (1.0 = full preservation).
    img = np.array(Image.open(CHECKERBOARD).convert("RGB"))
    mask = dither_region_mask(img)
    rendered = render(CHECKERBOARD, 1.0, tmpdir)
    dev = mean_deviation_from_source(rendered, img, mask)
    print(f"  [1] checkerboard-transparency, strength=1.0: mean |rendered-source| over dither region = {dev:.3f} "
          f"(want ~0, i.e. not blurred)")
    crit1 = dev < 1.0
    if not crit1:
        ok = False
    print(f"      PASS/FAIL (< 1.0 luma-ish unit, i.e. effectively unblurred): {'PASS' if crit1 else 'FAIL'}")

    # 2. Genesis-style manual dithering (dither_ramp's top half) visibly
    # preserved at strength=1.0.
    img2 = np.array(Image.open(DITHER_RAMP).convert("RGB"))
    zone_mask = np.array(Image.open(DITHER_RAMP_MASK).convert("L")) > 127
    h = img2.shape[0]
    top_zone = np.zeros_like(zone_mask)
    top_zone[: h // 2, :] = zone_mask[: h // 2, :]
    dither_mask2 = dither_region_mask(img2) & top_zone
    rendered2 = render(DITHER_RAMP, 1.0, tmpdir)
    dev2 = mean_deviation_from_source(rendered2, img2, dither_mask2)
    print(f"  [2] dither_ramp (Genesis-style, top half), strength=1.0: mean |rendered-source| = {dev2:.3f}")
    crit2 = dev2 < 1.0
    if not crit2:
        ok = False
    print(f"      PASS/FAIL: {'PASS' if crit2 else 'FAIL'}")

    # 3. Behavior differs measurably between hard (checkerboard/NES-Genesis)
    # and soft (SNES-style, dither_soft) dithering at a shared partial
    # strength, where hardness modulation actually has room to act.
    img3 = np.array(Image.open(SOFT_DITHER).convert("RGB"))
    mask3 = dither_region_mask(img3)
    rendered_hard_half = render(CHECKERBOARD, 0.5, tmpdir)
    rendered_soft_half = render(SOFT_DITHER, 0.5, tmpdir)
    dev_hard = mean_deviation_from_source(rendered_hard_half, img, mask)
    dev_soft = mean_deviation_from_source(rendered_soft_half, img3, mask3)
    print(f"  [3] strength=0.5: mean |rendered-source| over dither region — "
          f"hard(checkerboard)={dev_hard:.3f} soft(dither_soft)={dev_soft:.3f}")
    ratio = dev_soft / dev_hard if dev_hard else float("inf")
    crit3 = ratio > 1.5  # soft should be blended measurably more than hard; margin below the ~2.0x
                          # actually measured, so this isn't a knife-edge threshold on noise
    if not crit3:
        ok = False
    print(f"      ratio soft/hard = {ratio:.2f}")
    print(f"      PASS/FAIL (soft blended measurably more than hard, >1.5x): {'PASS' if crit3 else 'FAIL'}")

    return ok


def main():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        print("=== Numeric parity: shader vs. reference.py ===")
        tol_ok = check_tolerance(tmpdir)
        print()
        print("=== T-019 acceptance criteria (against rendered shader output) ===")
        acc_ok = check_acceptance_criteria(tmpdir)

    print()
    overall = tol_ok and acc_ok
    print(f"OVERALL: {'PASS' if overall else 'FAIL'}")
    sys.exit(0 if overall else 1)


if __name__ == "__main__":
    main()
