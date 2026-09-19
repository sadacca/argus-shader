"""T-046 — score an arbitrary single-pass argus-mobile-lite variant against
the same IoU ground-truth rubric as tools/eval_metric/rpg_text_eval.py, for
fast iterate-and-compare experimentation. Not part of the shipped eval
suite — this is a development tool for trying architecture/logic changes
and seeing their score impact before deciding whether to pursue them.

Usage: python3 tools/score_optimization/score_variant.py path/to/variant.slang [--label NAME]
"""
import argparse
import sys
import tempfile
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools" / "render_harness"))
sys.path.insert(0, str(REPO_ROOT / "tools" / "eval_metric"))
from render_pass import render_pass, parse_pragma_parameter_defaults  # noqa: E402
from rpg_text_eval import SCENES, NATIVE_W, NATIVE_H, SUPERSAMPLE, score  # noqa: E402
from PIL import Image  # noqa: E402


def score_variant(shader_path: Path) -> dict:
    params = parse_pragma_parameter_defaults(shader_path)
    results = {}
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        for scene_name, gen in SCENES.items():
            hi = gen()
            native = hi.resize((NATIVE_W, NATIVE_H), Image.Resampling.BOX)
            native_path = tmpdir / f"{scene_name}_native.png"
            native.save(native_path)
            gt_rgb = np.array(hi.convert("RGB"))

            recon = render_pass(shader_path, native_path, float(SUPERSAMPLE), tmpdir, params)[..., :3]
            iou, acc = score(recon, gt_rgb)
            results[scene_name] = (iou, acc)
    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("shader", type=Path)
    ap.add_argument("--label", default=None)
    args = ap.parse_args()
    label = args.label or args.shader.stem

    results = score_variant(args.shader)
    for scene_name, (iou, acc) in results.items():
        print(f"{label} / {scene_name}: {iou*100:.2f}% overlap, {acc*100:.2f}% px acc")


if __name__ == "__main__":
    main()
