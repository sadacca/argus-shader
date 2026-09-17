"""T-020 — verify the fused shipped shader (shaders/shaders_slang/argus/
shaders/mobile-lite.slang) against each of its four already-verified
contributing debug shaders, rather than re-deriving an independent CPU
model that risks its own transcription bugs. For each pixel, per its own
classification label (from classify_debug.slang's DEBUG_MODE=1), the fused
shader's output must match whichever standalone debug shader owns that
class's reconstruction rule, rendered on the identical image with matching
parameters. This checks the *fusion* — that combining four already-correct
rules into one file didn't introduce a transcription error — not the rules
themselves, which each already have their own verify_gpu.py.

Usage: python3 tools/fusion/verify_gpu.py
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools" / "render_harness"))

from render_pass import render_pass  # noqa: E402

FUSED = REPO_ROOT / "shaders" / "shaders_slang" / "argus" / "shaders" / "mobile-lite.slang"
CLASSIFY = REPO_ROOT / "tools" / "classifier_gpu" / "classify_debug.slang"
DITHER = REPO_ROOT / "tools" / "dither_reconstruct" / "dither_debug.slang"
TEXT = REPO_ROOT / "tools" / "text_protect" / "text_debug.slang"
EDGE = REPO_ROOT / "tools" / "edge_reconstruct" / "edge_debug.slang"

# Defaults, matching mobile-lite.slang's #pragma parameter defaults exactly.
DEFAULT_EDGE_THRESHOLD = 0.10
DEFAULT_DITHER_STRENGTH = 1.0

SAMPLES = [
    REPO_ROOT / "corpus/synthetic/dither_ramp/genesis_320x224.png",
    REPO_ROOT / "corpus/synthetic/text_positive/outlined_00.png",
    REPO_ROOT / "corpus/synthetic/diagonal_sweep/nes_256x240.png",
    REPO_ROOT / "corpus/synthetic/checkerboard_transparency/smw_256x224.png",
    REPO_ROOT / "corpus/synthetic/dither_soft/genesis_320x224.png",
]


def render(shader: Path, image_path: Path, tmpdir: Path, params: dict) -> np.ndarray:
    return render_pass(shader, image_path, 1.0, tmpdir, params)[..., :3].astype(np.int64)


def check_image(image_path: Path, tmpdir: Path) -> bool:
    labels = np.round(
        render(CLASSIFY, image_path, tmpdir, {"DEBUG_MODE": 1.0})[..., 0].astype(np.float64) / 255.0 * 3.0
    ).astype(int)

    fused = render(FUSED, image_path, tmpdir, {
        "ARGUS_EDGE_THRESHOLD": DEFAULT_EDGE_THRESHOLD,
        "ARGUS_DITHER_STRENGTH": DEFAULT_DITHER_STRENGTH,
    })
    dither_out = render(DITHER, image_path, tmpdir, {"ARGUS_DITHER_STRENGTH": DEFAULT_DITHER_STRENGTH})
    text_out = render(TEXT, image_path, tmpdir, {"DEBUG_MODE": 0.0})
    edge_out = render(EDGE, image_path, tmpdir, {"ARGUS_EDGE_THRESHOLD": DEFAULT_EDGE_THRESHOLD})

    ok = True
    checks = [
        ("dither (label 1)", labels == 1, dither_out),
        ("stroke (label 3)", labels == 3, text_out),
        ("edge/gradient (label 2)", labels == 2, edge_out),
    ]
    for name, mask, reference in checks:
        if not mask.any():
            print(f"  [{image_path.name}] {name}: no pixels in this class, skipped")
            continue
        diff = np.abs(fused - reference).max(axis=2)
        max_err = int(diff[mask].max())
        frac_over = float((diff[mask] > 2).mean())
        status = "OK" if frac_over < 0.01 else "FAIL"
        if status == "FAIL":
            ok = False
        print(f"  [{image_path.name}] {name}: n={int(mask.sum())} max_err={max_err} frac_over_tol={frac_over:.4f} {status}")

    flat_mask = labels == 0
    if flat_mask.any():
        centerish = fused  # flat pixels should equal the source's own color; check against source directly
        src = np.array(Image.open(image_path).convert("RGB")).astype(np.int64)
        diff = np.abs(fused - src).max(axis=2)
        max_err = int(diff[flat_mask].max())
        status = "OK" if max_err == 0 else "FAIL"
        if status == "FAIL":
            ok = False
        print(f"  [{image_path.name}] flat (label 0): n={int(flat_mask.sum())} max_err={max_err} {status}")

    return ok


def main():
    import tempfile
    ok = True
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        for path in SAMPLES:
            ok = check_image(path, tmpdir) and ok
    print()
    print(f"OVERALL: {'PASS' if ok else 'FAIL'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
