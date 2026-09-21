"""T-011 — render the RPG dialogue-box/letters content (generate_rpg_text.py)
through every baseline now actually runnable: nearest-neighbour (control),
Omniscale, SABR, ScaleFX, xBRZ, and argus-mobile-lite (T-020). SABR/ScaleFX/
xBRZ source is fetched from a scratch location outside this repo (see
docs/backlog-status.md's dated update for why: comparison output doesn't
require permanently vendoring GPL/MIT third-party shader *source* into this
project's own git history) — pass their local paths via the
--sabr/--scalefx/--xbrz arguments; without one, that baseline is skipped.

HQx is deliberately not included: it renders without error through
render_multipass.py but produces a visibly wrong result (a remaining bug
not yet isolated — see docs/backlog-status.md), and it's also the most
legally marginal of the three previously-copyleft-blocked baselines per
docs/licensing.md ("conditional; default to no-go"), so it wasn't worth
chasing further to include here.

Usage:
  python3 tools/comparison/generate_rpg_baselines.py \\
      --sabr /path/to/sabr-v3.0.slang \\
      --scalefx tools/comparison/reference_shaders/scalefx/scalefx.slangp \\
      --xbrz /path/to/2xbrz-linear.slangp \\
      --out /tmp/rpg_baselines --scale 4
"""
import argparse
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools" / "render_harness"))
from render_pass import render_pass, parse_pragma_parameter_defaults  # noqa: E402
from render_multipass import run_preset  # noqa: E402

CONTENT = [
    REPO_ROOT / "corpus" / "synthetic" / "rpg_text" / "rpg_dialogue_box.png",
    REPO_ROOT / "corpus" / "synthetic" / "rpg_text" / "rpg_letters.png",
]
MOBILE_LITE = REPO_ROOT / "shaders" / "shaders_slang" / "argus" / "experimental" / "shaders" / "mobile-lite.slang"
OMNISCALE = REPO_ROOT / "tools" / "edge_reconstruct" / "reference_shaders" / "omniscale.slang"


def nearest_neighbour(src_path: Path, scale: int) -> np.ndarray:
    img = Image.open(src_path).convert("RGBA")
    return np.array(img.resize((img.width * scale, img.height * scale), Image.Resampling.NEAREST))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sabr", type=Path, default=None)
    ap.add_argument("--scalefx", type=Path, default=None)
    ap.add_argument("--xbrz", type=Path, default=None)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--scale", type=int, default=4)
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    mobile_lite_params = parse_pragma_parameter_defaults(MOBILE_LITE)

    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        for content_path in CONTENT:
            stem = content_path.stem
            print(f"=== {stem} ===")

            nn = nearest_neighbour(content_path, args.scale)
            Image.fromarray(nn).save(args.out / f"{stem}__nearest-neighbour.png")
            print("  nearest-neighbour: done")

            omni = render_pass(OMNISCALE, content_path, float(args.scale), tmpdir, {})
            Image.fromarray(omni, mode="RGBA").save(args.out / f"{stem}__omniscale.png")
            print("  omniscale: done")

            argus = render_pass(MOBILE_LITE, content_path, float(args.scale), tmpdir, mobile_lite_params)
            Image.fromarray(argus, mode="RGBA").save(args.out / f"{stem}__argus-mobile-lite.png")
            print("  argus-mobile-lite: done")

            if args.sabr:
                sabr = render_pass(args.sabr, content_path, float(args.scale), tmpdir, {})
                Image.fromarray(sabr, mode="RGBA").save(args.out / f"{stem}__sabr.png")
                print("  sabr: done")

            if args.scalefx:
                sfx = run_preset(args.scalefx, content_path, float(args.scale) * (3.0 / 3.0), tmpdir)
                # ScaleFX's own final pass upscales 3x internally regardless
                # of --scale; run_preset's `out_scale` only matters for any
                # scale_type=viewport pass, which this preset doesn't use —
                # its real output scale is fixed at 3x by its own pass5.
                Image.fromarray(sfx, mode="RGBA").save(args.out / f"{stem}__scalefx.png")
                print(f"  scalefx: done (note: ScaleFX's own preset is fixed at 3x, not --scale)")

            if args.xbrz:
                xbrz = run_preset(args.xbrz, content_path, float(args.scale), tmpdir)
                Image.fromarray(xbrz, mode="RGBA").save(args.out / f"{stem}__xbrz.png")
                print("  xbrz: done")

    print(f"\nAll renders written under {args.out}")


if __name__ == "__main__":
    main()
