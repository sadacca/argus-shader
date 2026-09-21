"""Gold-standard hard-case eval — scores every executable baseline against
both ground-truth regimes generate_shapes.py builds (vector-source-recovery
and blocky-art-preservation) on the V-corner and O-ring shapes. See
generate_shapes.py's module docstring for the full methodology and why.

Also checks every "argus-*" candidate's scores against the numeric fidelity
gates in gates.py (docs/backlog.md's Track F) and prints/reports the result.
Exits non-zero if any argus-* candidate fails the regression guard — that
gate should already be passing (it's set to xBRZ's own 8bit score, and the
retired prototype clears it comfortably) and a failure there means a real
regression, not incomplete progress. The primary/interim fidelity gates are
tracked and reported but do NOT fail the build: until Track F lands, no
candidate is expected to clear them, and a build that's red for known,
in-progress work just teaches everyone to ignore red builds.

SABR/xBRZ source is expected at scratch paths outside this repo, same as
tools/comparison/generate_rpg_baselines.py; pass their paths via
--sabr/--xbrz. ScaleFX is vendored in-repo (MIT). argus-cpu-ref (F-1) needs
neither a shader compile nor a GPU — see cpu_reference.py.

Usage:
  python3 tools/gold_eval/run_eval.py \\
      --sabr /path/to/sabr-v3.0.slang --xbrz /path/to/2xbrz-linear.slangp
"""
import argparse
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
from generate_shapes import SHAPES, SUPERSAMPLE, NATIVE_SIZE, HIGH_RES  # noqa: E402
from scoring import score, label, contact_sheet, nearest_neighbour  # noqa: E402
from cpu_reference import reconstruct as cpu_reconstruct, parse_pragma_parameter_defaults  # noqa: E402
import gates  # noqa: E402

SHAPES_DIR = Path(__file__).resolve().parent / "shapes"
AUDIT_DIR = Path(__file__).resolve().parent / "audit"

MOBILE_LITE = REPO_ROOT / "shaders" / "shaders_slang" / "argus" / "experimental" / "shaders" / "mobile-lite.slang"
OMNISCALE = REPO_ROOT / "tools" / "edge_reconstruct" / "reference_shaders" / "omniscale.slang"
SCALEFX = REPO_ROOT / "tools" / "comparison" / "reference_shaders" / "scalefx" / "scalefx.slangp"

_gpu_funcs = None


def _gpu():
    """Lazy import of render_pass/render_multipass — both pull in PyOpenGL
    and egl_context.py's module-level `ctypes.CDLL("libEGL.so.1")`, which
    raises OSError on any machine without a GLES/EGL userspace installed.
    Deferring this means --skip-gpu (nearest-neighbour + argus-cpu-ref, F-1)
    runs in environments that have never installed that stack at all —
    exactly the environment this repo's own dev loop was missing (docs/
    backlog.md P-5)."""
    global _gpu_funcs
    if _gpu_funcs is None:
        sys.path.insert(0, str(REPO_ROOT / "tools" / "render_harness"))
        from render_pass import render_pass  # noqa: E402
        from render_multipass import run_preset  # noqa: E402
        _gpu_funcs = (render_pass, run_preset)
    return _gpu_funcs


def run_candidate(name: str, native_path: Path, tmpdir: Path, mobile_lite_params: dict, args) -> np.ndarray:
    if name == "nearest-neighbour":
        return nearest_neighbour(Image.open(native_path), SUPERSAMPLE)
    if name == "argus-cpu-ref":
        native_rgb = np.array(Image.open(native_path).convert("RGB"))
        return cpu_reconstruct(native_rgb, SUPERSAMPLE, mobile_lite_params)
    if name == "omniscale":
        render_pass, _ = _gpu()
        return render_pass(OMNISCALE, native_path, float(SUPERSAMPLE), tmpdir, {})[..., :3]
    if name == "argus-mobile-lite":
        render_pass, _ = _gpu()
        return render_pass(MOBILE_LITE, native_path, float(SUPERSAMPLE), tmpdir, mobile_lite_params)[..., :3]
    if name == "sabr" and args.sabr:
        render_pass, _ = _gpu()
        return render_pass(args.sabr, native_path, float(SUPERSAMPLE), tmpdir, {})[..., :3]
    if name == "scalefx":
        _, run_preset = _gpu()
        recon = run_preset(SCALEFX, native_path, float(SUPERSAMPLE), tmpdir)[..., :3]
        if recon.shape[:2] != (HIGH_RES, HIGH_RES):
            recon = np.array(Image.fromarray(recon).resize((HIGH_RES, HIGH_RES), Image.Resampling.NEAREST))
        return recon
    if name == "xbrz" and args.xbrz:
        _, run_preset = _gpu()
        recon = run_preset(args.xbrz, native_path, float(SUPERSAMPLE), tmpdir)[..., :3]
        if recon.shape[:2] != (HIGH_RES, HIGH_RES):
            recon = np.array(Image.fromarray(recon).resize((HIGH_RES, HIGH_RES), Image.Resampling.NEAREST))
        return recon
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sabr", type=Path, default=None)
    ap.add_argument("--xbrz", type=Path, default=None)
    ap.add_argument("--skip-gpu", action="store_true",
                     help="skip every candidate that needs glslangValidator/EGL "
                          "(nearest-neighbour + argus-cpu-ref only) — for environments "
                          "without the GLES toolchain installed")
    args = ap.parse_args()

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    if args.skip_gpu:
        candidates = ["nearest-neighbour", "argus-cpu-ref"]
    else:
        candidates = ["nearest-neighbour", "omniscale", "argus-mobile-lite", "argus-cpu-ref", "scalefx"]
        if args.sabr:
            candidates.insert(-1, "sabr")
        if args.xbrz:
            candidates.append("xbrz")

    results = {"vector": {}, "8bit": {}}

    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        mobile_lite_params = parse_pragma_parameter_defaults(MOBILE_LITE)

        for shape_name in SHAPES:
            # --- vector regime ---
            gt_path = SHAPES_DIR / "vector" / f"{shape_name}_groundtruth_{HIGH_RES}px.png"
            native_path = SHAPES_DIR / "vector" / f"{shape_name}_native_{NATIVE_SIZE}px.png"
            gt_rgb = np.array(Image.open(gt_path).convert("RGB"))
            cells = [label(Image.open(gt_path), "ground truth (vector, supersampled)")]
            row = {}
            for name in candidates:
                recon = run_candidate(name, native_path, tmpdir, mobile_lite_params, args)
                if recon is None:
                    continue
                iou, acc = score(recon, gt_rgb)
                row[name] = (iou, acc)
                cells.append(label(Image.fromarray(recon), f"{name}: {iou*100:.1f}%"))
                print(f"[vector] {shape_name} / {name}: {iou*100:.2f}% overlap, {acc*100:.2f}% px acc")
            results["vector"][shape_name] = row
            contact_sheet(cells).save(AUDIT_DIR / f"{shape_name}_vector.png")

            # --- 8bit regime ---
            native_8bit_path = SHAPES_DIR / "8bit" / f"{shape_name}_native_{NATIVE_SIZE}px.png"
            gt_8bit_rgb = nearest_neighbour(Image.open(native_8bit_path), SUPERSAMPLE)
            cells = [label(Image.fromarray(gt_8bit_rgb), "ground truth (8bit, NN-preserved)")]
            row = {}
            for name in candidates:
                recon = run_candidate(name, native_8bit_path, tmpdir, mobile_lite_params, args)
                if recon is None:
                    continue
                iou, acc = score(recon, gt_8bit_rgb)
                row[name] = (iou, acc)
                cells.append(label(Image.fromarray(recon), f"{name}: {iou*100:.1f}%"))
                print(f"[8bit]   {shape_name} / {name}: {iou*100:.2f}% overlap, {acc*100:.2f}% px acc")
            results["8bit"][shape_name] = row
            contact_sheet(cells).save(AUDIT_DIR / f"{shape_name}_8bit.png")

    write_report(results, candidates)

    argus_candidates = [c for c in candidates if c.startswith("argus")]
    all_gate_results = {}
    build_should_fail = False
    print()
    for candidate in argus_candidates:
        gate_results = gates.check_gates(results, candidate)
        all_gate_results[candidate] = gate_results
        print(gates.format_gate_report(candidate, gate_results))
        regression = gate_results.get("regression_guard")
        if regression and not gates.gate_passed(regression):
            build_should_fail = True
        print()

    append_gate_section(all_gate_results)
    sys.exit(1 if build_should_fail else 0)


def write_report(results: dict, candidates: list):
    lines = [
        "# Gold-standard hard-case eval — V-corner / O-ring, two ground-truth regimes",
        "",
        "Generated by `run_eval.py`. See `generate_shapes.py` for full methodology. Two regimes, "
        "same shapes: **vector** (a true smooth source exists, box-downsampled to native — rewards "
        "recovering the smooth edge) and **8bit** (drawn blocky at native resolution directly, no "
        "hidden smooth source — rewards *not* smoothing something that was never meant to be smooth).",
        "",
    ]
    for regime in ("vector", "8bit"):
        lines += [f"## {regime} regime", "", "| shape | " + " | ".join(candidates) + " |",
                  "|---|" + "---:|" * len(candidates)]
        for shape_name, row in results[regime].items():
            cells = [f"{row[c][0]*100:.1f}%" if c in row else "—" for c in candidates]
            lines.append(f"| {shape_name} | " + " | ".join(cells) + " |")
        lines.append("")

    lines += [
        "## Reading this honestly",
        "",
        "**On the vector regime (a real smooth source exists), argus-mobile-lite is the worst or "
        "second-worst candidate on both hard shapes** — it ties or loses to plain nearest-neighbour "
        "(80.5% vs 81.0% on v_corner; a marginal 82.9% vs 82.3% on o_ring), while xBRZ/SABR/ScaleFX "
        "all clear a real, substantial margin over nearest-neighbour (SABR +9-10pp, xBRZ +12-13pp). "
        "Visual audit (`audit/v_corner_vector.png`) shows why: argus's reconstruction is nearly "
        "indistinguishable from blocky nearest-neighbour, plus a visible cross-hatch artifact right "
        "at the sharp vertex — the exact hard case this eval targeted. On genuinely curved/angled "
        "content with a real smooth source (most SNES-era pre-rendered art, gradients, glow effects), "
        "argus-mobile-lite provides close to zero benefit over doing nothing.",
        "",
        "**On the 8bit regime (no hidden smooth source — genuine blocky pixel art), the picture "
        "reverses: argus-mobile-lite is the best of every real candidate** at leaving intentionally-"
        "blocky art alone (93.0-93.6%, clearly ahead of Omniscale/SABR/xBRZ's 84-88% and ScaleFX's "
        "80-82%) — nearest-neighbour's 100% is tautological (it IS the ground truth here by "
        "construction), not a competing result. This is real, measured evidence that T-016/T-017's "
        "classifier and nearest-preserving reconstruction do what they were built to do.",
        "",
        "**Both are true at once, and neither should be cited alone.** argus-mobile-lite is "
        "measurably the best available candidate at its one specific design goal (don't smooth "
        "deliberate pixel art) and measurably the worst at the complementary, equally-common case "
        "(recover a real smooth edge) — where every competing algorithm is actually optimized. Real "
        "game content is a mix of both regimes, not one or the other, which is consistent with real "
        "screenshots looking worse overall despite this project's own narrower synthetic tests "
        "showing a near-tie.",
        "",
        "**Since the v0.3 pivot (docs/requirements.md), this is read differently**: the above is the "
        "evidence base for retiring the preservation goal, not a target to protect. `argus-cpu-ref` "
        "(F-1, docs/backlog.md) reproduces argus-mobile-lite's numbers exactly and is now the fast "
        "iteration surface for the fidelity work that replaces it — see the gate status below.",
    ]

    out = Path(__file__).resolve().parent / "report.md"
    out.write_text("\n".join(lines) + "\n")
    print(f"\nwrote {out}")


def append_gate_section(all_gate_results: dict):
    out = Path(__file__).resolve().parent / "report.md"
    lines = ["", "## Fidelity gate status (docs/backlog.md Track F)", ""]
    for candidate, gate_results in all_gate_results.items():
        lines.append(f"### {candidate}")
        lines.append("```")
        lines.append(gates.format_gate_report(candidate, gate_results))
        lines.append("```")
        lines.append("")
    with out.open("a") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
