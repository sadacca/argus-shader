#!/usr/bin/env python3
"""T-040 — legacy `.glsl` compile gate.

Counterpart to compile_check.py for RetroArch's older GLSL shader driver
format (single file, `#if defined(VERTEX)`/`#elif defined(FRAGMENT)`
conditional compilation, COMPAT_* macros, implicit non-Vulkan uniform
bindings — see docs/backlog.md T-040). This format isn't Vulkan-semantics
GLSL, so it doesn't go through glslangValidator's -V/SPIR-V path at all
(unlike compile_check.py's slang gate) — it's compiled directly, the same
way RetroArch's own gl_glsl_compile_shader() assembles it.

T-045 rewrite, replacing the previous version of this gate: that version
tested five profiles by externally forcing a `#version` line in front of
the file's own text ("#version 310 es\n#define VERTEX\n" + file contents).
That stopped being *possible* once the file itself started declaring its
own `#version` (T-045 — GLSL forbids two `#version` directives), and more
importantly it was never actually representative of real RetroArch
behavior: `gl_glsl_compile_shader()` (gfx/drivers_shader/shader_glsl.c,
read from github.com/libretro/RetroArch master branch, 2026-09-19) does not
take whatever version an embedder wants — if the file declares its own
`#version N`, the driver *strips* that line and substitutes a version it
computes from N, and the substitution differs by target:

  - GLES3-capable target (the real T-005 floor this project ships for):
    N in [130, 330) -> "300 es"; N == 330 -> "310 es"; N > 330 -> "320 es".
  - GLES-2-only target (outside T-005's device matrix): always "100",
    regardless of what N is.
  - Desktop (non-ES) target: N is used verbatim ("#version N").

So what actually gets compiled depends on the *number this file declares*,
not on some external test harness's choice — this gate now simulates that
substitution exactly, for the file's real declared version, rather than
picking its own versions to try.

Usage: python3 tools/compile_gate/compile_check_legacy.py [file.glsl ...]
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TARGETS = list((REPO_ROOT / "shaders").glob("shaders_glsl/**/*.glsl"))

REQUIRED_TOOLS = ["glslangValidator"]

# Always defined by gl_glsl_compile_shader() for every stage, alongside
# VERTEX/FRAGMENT (see its `#define VERTEX\n#define PARAMETER_UNIFORM\n...`
# literal in gl_glsl_compile_program()) — included so files that read
# `#ifdef PARAMETER_UNIFORM` are tested on the code path real RetroArch
# actually takes (uniform-bound, tunable parameters), not the compile-time-
# constant fallback branch.
ALWAYS_DEFINED = [
    "PARAMETER_UNIFORM", "_HAS_ORIGINALASPECT_UNIFORMS",
    "_HAS_FRAMETIME_UNIFORMS", "_HAS_SENSOR_UNIFORMS", "_HAS_SWAPCOUNT_UNIFORM",
]

_VERSION_RE = re.compile(r'^\s*#version\s+(\d+)\s*\n', re.MULTILINE)


def remap_gles3(declared: int) -> str:
    if 130 <= declared < 330:
        return "300 es"
    if declared == 330:
        return "310 es"
    if declared > 330:
        return "320 es"
    return "100"  # declared < 130: driver treats as "not a real version request"


# (label, version-string, gating) — gating=False means a failure here is
# expected/informative, not a gate failure: this project's own T-005 floor
# (docs/gles-floor.md) already decided GLES 3.1+ core, gather-only, no
# GLES 3.0 or GLES 2.0 fallback — those two profiles exist only to keep
# this file's real, verified behavior on record for frontends/devices
# outside this project's target matrix, not to require support for them.
def build_targets(declared_version: int):
    return [
        ("Desktop GL (declared version used verbatim by the real driver)",
         f"#version {declared_version}\n", True),
        ("GLES3.1+ mobile — the real T-005 target "
         f"(declared {declared_version} remaps to {remap_gles3(declared_version)})",
         f"#version {remap_gles3(declared_version)}\n", True),
        ("GLES-2-only target (outside T-005's matrix; real driver always forces "
         "\"100\" here regardless of declared version)",
         "#version 100\n", False),
    ]


def check_tools() -> None:
    missing = [t for t in REQUIRED_TOOLS if shutil.which(t) is None]
    if missing:
        print(f"ERROR: required tools not on PATH: {', '.join(missing)}")
        sys.exit(2)


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def strip_declared_version(text: str) -> tuple:
    """Mirrors gl_glsl_compile_shader()'s `existing_version` handling: find
    the file's own `#version N` line, and return (N, rest-of-file-without-
    that-line) — the same split the real driver performs before it
    substitutes its own computed version line back in front."""
    m = _VERSION_RE.match(text)
    if not m:
        return None, text
    return int(m.group(1)), text[m.end():]


def compile_stage(rest_of_file: str, version_line: str, stage_define: str, stage_flag: str,
                   tmpdir: Path, ext: str):
    defines = "".join(f"#define {d}\n" for d in [stage_define] + ALWAYS_DEFINED)
    src = tmpdir / f"stage.{ext}"
    src.write_text(f"{version_line}{defines}{rest_of_file}")
    return run(["glslangValidator", "-S", stage_flag, str(src)])


def check_file(path: Path) -> bool:
    text = path.read_text()
    declared, rest = strip_declared_version(text)
    if declared is None:
        print(f"FAIL {path}: no `#version` line — real RetroArch injects none either in this case, "
              "so the file would compile under the implicit GLSL ES 1.00 default (see T-045)")
        return False

    ok = True
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        for label, version_line, gating in build_targets(declared):
            stage_ok = True
            for stage_define, stage_flag, ext in (("VERTEX", "vert", "vert"), ("FRAGMENT", "frag", "frag")):
                r = compile_stage(rest, version_line, stage_define, stage_flag, tmpdir, ext)
                if r.returncode != 0:
                    tag = "FAIL" if gating else "INFO (non-gating)"
                    print(f"{tag} {path} [{label}/{stage_define}]:\n{r.stdout}{r.stderr}")
                    stage_ok = False
            if not stage_ok and gating:
                ok = False
    if ok:
        print(f"PASS {path}: all gating targets compile clean (vertex + fragment); "
              f"declared version {declared}")
    return ok


def main():
    check_tools()
    targets = [Path(a) for a in sys.argv[1:]] or DEFAULT_TARGETS
    if not targets:
        print("no .glsl targets found")
        sys.exit(0)
    results = [check_file(t) for t in targets]
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
