"""F-1 (docs/backlog.md) acceptance check — no shader compile, no GPU,
no EGL/OpenGL import anywhere in this process's import graph.

Validates that cpu_reference.reconstruct() (a numpy port of the retired
mobile-lite.slang) reproduces the GPU-rendered scores already published in
tools/gold_eval/report.md, within +/-0.5 percentage points, and that the
full four-shape sweep (2 shapes x 2 regimes) runs in under 5 seconds. If
this passes, the CPU path is trustworthy as the fast iteration surface for
F-2/F-3; if it doesn't, cpu_reference.py has a real bug, not the algorithm
under test.

Usage: python3 tools/gold_eval/validate_cpu_reference.py
"""
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

from generate_shapes import SHAPES, SUPERSAMPLE, NATIVE_SIZE, HIGH_RES
from cpu_reference import reconstruct, parse_pragma_parameter_defaults
from scoring import nearest_neighbour, score

SHAPES_DIR = Path(__file__).resolve().parent / "shapes"
TOLERANCE_PP = 0.5

# From tools/gold_eval/report.md's "argus-mobile-lite" column, as published.
PUBLISHED = {
    "vector": {"v_corner": 80.5, "o_ring": 82.9},
    "8bit": {"v_corner": 93.6, "o_ring": 93.0},
}


def main():
    params = parse_pragma_parameter_defaults()
    print(f"params: {params}")

    t0 = time.perf_counter()
    measured = {"vector": {}, "8bit": {}}

    for shape_name in SHAPES:
        gt_path = SHAPES_DIR / "vector" / f"{shape_name}_groundtruth_{HIGH_RES}px.png"
        native_path = SHAPES_DIR / "vector" / f"{shape_name}_native_{NATIVE_SIZE}px.png"
        gt_rgb = np.array(Image.open(gt_path).convert("RGB"))
        native_rgb = np.array(Image.open(native_path).convert("RGB"))
        recon = reconstruct(native_rgb, SUPERSAMPLE, params)
        iou, _ = score(recon, gt_rgb)
        measured["vector"][shape_name] = iou * 100.0

        native_8bit_path = SHAPES_DIR / "8bit" / f"{shape_name}_native_{NATIVE_SIZE}px.png"
        native_8bit_rgb = np.array(Image.open(native_8bit_path).convert("RGB"))
        gt_8bit_rgb = nearest_neighbour(Image.open(native_8bit_path), SUPERSAMPLE)
        recon_8bit = reconstruct(native_8bit_rgb, SUPERSAMPLE, params)
        iou_8bit, _ = score(recon_8bit, gt_8bit_rgb)
        measured["8bit"][shape_name] = iou_8bit * 100.0

    elapsed = time.perf_counter() - t0

    ok = True
    for regime in ("vector", "8bit"):
        for shape_name in SHAPES:
            m = measured[regime][shape_name]
            p = PUBLISHED[regime][shape_name]
            delta = abs(m - p)
            status = "OK" if delta <= TOLERANCE_PP else "MISMATCH"
            if delta > TOLERANCE_PP:
                ok = False
            print(f"[{regime}] {shape_name}: cpu={m:.2f}%  published(gpu)={p:.2f}%  "
                  f"delta={delta:.2f}pp  [{status}]")

    print(f"\nfour-shape sweep: {elapsed:.2f}s (gate: < 5.0s)")
    if elapsed >= 5.0:
        ok = False
        print("FAIL: sweep too slow")

    if ok:
        print("\nF-1 PASS: CPU reference is faithful to the published GPU baseline and fast enough "
              "to be the iteration surface for F-2/F-3.")
    else:
        print("\nF-1 FAIL: see mismatches above.")

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
