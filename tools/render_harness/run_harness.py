"""T-003 — headless golden-image regression harness.

Iterates every (content, preset) tuple, renders each through the real
GLES cross-compile (see render_pass.py), and either checks the result
against a committed golden (default) or writes a new golden (--update-
goldens, an explicit flag — golden updates are never automatic per T-003's
acceptance criteria).

Backend scope, honestly stated: this only renders through GLES (via the
headless EGL_EXT_platform_device / llvmpipe path — see egl_context.py).
T-002's compile gate already validates that every pass parses and
cross-compiles clean for GL, GLES, D3D11/12, Metal and Vulkan/SPIR-V, but
this harness does not *execute* the GL-desktop, D3D, Metal, or Vulkan
outputs — no D3D/Metal runtime exists on this platform, and a Vulkan
render path (distinct boilerplate from EGL/GLES) hasn't been built yet.
"Runs against all backends from T-002" (the ticket's fourth acceptance box)
is therefore only partially met; see docs/backlog-status.md for what's left.

Only single-pass presets are supported (matches every preset shipped so
far); a preset with shaders > 1 is skipped with a warning.
"""
import argparse
import re
import sys
import tempfile
from pathlib import Path

from render_pass import render_pass, parse_pragma_parameter_defaults
from compare_golden import compare
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
PRESET_DIRS = [REPO_ROOT / "shaders" / "shaders_slang" / "argus"]
CORPUS_DIR = REPO_ROOT / "corpus" / "synthetic"
GOLDENS_DIR = Path(__file__).resolve().parent / "goldens"


def parse_preset(slangp_path: Path):
    text = slangp_path.read_text()
    n_shaders_match = re.search(r"^\s*shaders\s*=\s*(\d+)", text, re.MULTILINE)
    n_shaders = int(n_shaders_match.group(1)) if n_shaders_match else 0
    shader0_match = re.search(r"^\s*shader0\s*=\s*(\S+)", text, re.MULTILINE)
    scale0_match = re.search(r"^\s*scale0\s*=\s*([\d.]+)", text, re.MULTILINE)
    shader0 = slangp_path.parent / shader0_match.group(1) if shader0_match else None
    scale0 = float(scale0_match.group(1)) if scale0_match else 1.0
    return n_shaders, shader0, scale0


def discover_presets():
    presets = []
    for d in PRESET_DIRS:
        for slangp in sorted(d.glob("*.slangp")):
            n_shaders, shader0, scale0 = parse_preset(slangp)
            if n_shaders != 1:
                print(f"SKIP {slangp.name}: {n_shaders}-pass preset not supported by this harness yet")
                continue
            presets.append((slangp.stem, shader0, scale0))
    return presets


def discover_content():
    return sorted(CORPUS_DIR.rglob("*.png"))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--update-goldens", action="store_true",
                     help="write rendered frames as the new goldens instead of checking against them")
    ap.add_argument("--tolerance", type=int, default=0)
    args = ap.parse_args()

    presets = discover_presets()
    content = discover_content()
    if not presets:
        print("no single-pass presets found")
        sys.exit(1)
    if not content:
        print("no corpus content found")
        sys.exit(1)

    n_pass = n_fail = n_new = 0
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        for preset_name, shader0, scale0 in presets:
            # T-020: render at each parameter's declared #pragma parameter
            # default, not an implicit all-zero — see
            # parse_pragma_parameter_defaults()'s docstring for why this
            # started mattering only once a shipped shader (mobile-lite.slang)
            # actually read its own parameters.
            param_defaults = parse_pragma_parameter_defaults(shader0)
            for content_path in content:
                rel = content_path.relative_to(CORPUS_DIR)
                golden_path = GOLDENS_DIR / preset_name / rel

                frame = render_pass(shader0, content_path, scale0, tmpdir, param_defaults)

                if args.update_goldens:
                    golden_path.parent.mkdir(parents=True, exist_ok=True)
                    Image.fromarray(frame, mode="RGBA").save(golden_path)
                    print(f"UPDATED golden: {preset_name}/{rel}")
                    n_new += 1
                    continue

                rendered_path = tmpdir / f"render_{preset_name}_{rel.as_posix().replace('/', '_')}"
                Image.fromarray(frame, mode="RGBA").save(rendered_path)
                code, message = compare(rendered_path, golden_path, args.tolerance)
                tag = f"[{preset_name}/{rel}]"
                if code == 0:
                    n_pass += 1
                else:
                    print(f"{tag} {message}")
                    n_fail += 1

    if args.update_goldens:
        print(f"\n{n_new} golden(s) written under {GOLDENS_DIR}")
        return

    total = n_pass + n_fail
    print(f"\n{n_pass}/{total} tuples matched their golden")
    sys.exit(0 if n_fail == 0 else 1)


if __name__ == "__main__":
    main()
