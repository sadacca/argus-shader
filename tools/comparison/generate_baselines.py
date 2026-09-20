"""T-011 — render the synthetic corpus through every baseline this project
can currently execute (T-020's shipped mobile-lite pass, Omniscale, and
nearest-neighbour) at a matched output scale, into per-baseline directories
with matching filenames — ready to load pairwise into tools/ab_compare/
index.html (T-012) for a visual A/B, or to diff programmatically.

ScaleFX (MIT, cleared per docs/licensing.md) is vendored under
reference_shaders/ but NOT rendered here: it's a 6-pass filter chain with
named cross-pass texture aliasing, and this project's render harness is
single-pass only (see render_pass.py/run_harness.py docstrings) — see
reference_shaders/NOTICE.md and report.md for detail. xBRZ/SABR/HQx are not
vendored at all (copyleft, gated on a licensing-scope decision T-011
already flags as needing human input — see docs/licensing.md).

Usage: python3 tools/comparison/generate_baselines.py [--scale 4.0]
"""
import argparse
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools" / "render_harness"))

from render_pass import render_pass, parse_pragma_parameter_defaults  # noqa: E402

MOBILE_LITE = REPO_ROOT / "shaders" / "shaders_slang" / "argus" / "experimental" / "shaders" / "mobile-lite.slang"
OMNISCALE = REPO_ROOT / "tools" / "edge_reconstruct" / "reference_shaders" / "omniscale.slang"
CORPUS_DIR = REPO_ROOT / "corpus" / "synthetic"
OUT_DIR = Path(__file__).resolve().parent / "renders"


def discover_content():
    # Excludes *_mask.png (reference masks, not renderable content) —
    # unlike run_harness.py's discover_content(), which picks them up too
    # (an existing quirk in that file, not repeated here since a comparison
    # set specifically wants real content only).
    return sorted(p for p in CORPUS_DIR.rglob("*.png") if not p.stem.endswith("_mask"))


def nearest_neighbour(image_path: Path, scale: float) -> np.ndarray:
    img = Image.open(image_path).convert("RGBA")
    return np.array(img.resize((int(img.width * scale), int(img.height * scale)), Image.NEAREST))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scale", type=float, default=4.0,
                     help="matches argus-mobile-lite.slangp's scale0 (default 4.0) so the "
                          "argus-mobile-lite baseline can reuse tools/render_harness/goldens "
                          "directly instead of re-rendering")
    args = ap.parse_args()

    content = discover_content()
    if not content:
        print("no corpus content found")
        sys.exit(1)

    mobile_lite_params = parse_pragma_parameter_defaults(MOBILE_LITE)

    baselines = {
        "nearest-neighbour": None,  # rendered with PIL, not through the harness
        "omniscale": OMNISCALE,
        "argus-mobile-lite": MOBILE_LITE,
    }

    n_written = 0
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        for name, shader in baselines.items():
            for content_path in content:
                rel = content_path.relative_to(CORPUS_DIR)
                dst = OUT_DIR / name / rel
                dst.parent.mkdir(parents=True, exist_ok=True)

                if shader is None:
                    frame = nearest_neighbour(content_path, args.scale)
                else:
                    params = mobile_lite_params if shader is MOBILE_LITE else {}
                    frame = render_pass(shader, content_path, args.scale, tmpdir, params)

                Image.fromarray(frame).save(dst)
                n_written += 1

    print(f"{n_written} images written under {OUT_DIR} "
          f"({len(baselines)} baselines x {len(content)} corpus items, scale={args.scale})")
    print("Load any two baseline directories into tools/ab_compare/index.html for a visual A/B.")


if __name__ == "__main__":
    main()
