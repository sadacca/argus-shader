"""T-003 — per-tuple pixel-delta diff of a rendered frame against a committed
golden. Exit 0 (match), 1 (mismatch, with a delta report), or 2 (no golden
on record — never silently treated as a pass or auto-created; see
run_harness.py's explicit --update-goldens)."""
import sys
from pathlib import Path

import numpy as np
from PIL import Image


def compare(rendered_path: Path, golden_path: Path, tolerance: int = 0):
    """tolerance: max allowed per-channel abs delta for a pixel to still
    count as matching (0 = exact, appropriate for the current passthrough
    skeletons; later reconstruction passes across backends may need a small
    nonzero tolerance for float-rounding differences)."""
    if not golden_path.exists():
        return 2, f"NO GOLDEN {golden_path}"

    rendered = np.array(Image.open(rendered_path).convert("RGBA"), dtype=np.int16)
    golden = np.array(Image.open(golden_path).convert("RGBA"), dtype=np.int16)

    if rendered.shape != golden.shape:
        return 1, f"SHAPE MISMATCH {rendered_path}: rendered {rendered.shape} vs golden {golden.shape}"

    delta = np.abs(rendered - golden)
    mismatched = np.any(delta > tolerance, axis=-1)
    n_mismatched = int(mismatched.sum())
    if n_mismatched == 0:
        return 0, f"MATCH {rendered_path} (tolerance={tolerance})"

    total = mismatched.size
    max_delta = int(delta.max())
    pct = 100.0 * n_mismatched / total
    return 1, (
        f"MISMATCH {rendered_path}: {n_mismatched}/{total} px differ ({pct:.3f}%), "
        f"max per-channel delta={max_delta}"
    )


def main():
    if len(sys.argv) not in (3, 4):
        print("usage: compare_golden.py <rendered.png> <golden.png> [tolerance]")
        sys.exit(2)
    rendered_path = Path(sys.argv[1])
    golden_path = Path(sys.argv[2])
    tolerance = int(sys.argv[3]) if len(sys.argv) == 4 else 0
    code, message = compare(rendered_path, golden_path, tolerance)
    print(message)
    sys.exit(code)


if __name__ == "__main__":
    main()
