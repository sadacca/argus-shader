#!/usr/bin/env python3
"""T-040 — legacy `.glsl` compile gate.

Counterpart to compile_check.py for RetroArch's older GLSL shader driver
format (single file, `#if defined(VERTEX)`/`#elif defined(FRAGMENT)`
conditional compilation, COMPAT_* macros, implicit non-Vulkan uniform
bindings — see docs/backlog.md T-040). This format isn't Vulkan-semantics
GLSL, so it doesn't go through glslangValidator's -V/SPIR-V path at all
(unlike compile_check.py's slang gate) — it's compiled directly, the same
way RetroArch's own gl_glsl_compile_shader() assembles it: a `#version`
line, then a `#define VERTEX` or `#define FRAGMENT`, then the file verbatim.

Checked against four target profiles, matching the ES-vs-desktop and
GLSL-version splits the legacy driver's COMPAT_* macros are written to
support:
  - GLSL ES 300 (GLES3 mobile path — the actual target per docs/gles-floor.md,
    T-005, which floors this project at GLES 3.1+ core, gather-only, no
    GLES 3.0 fallback)
  - GLSL ES 100 (older GLES2 devices outside this project's target matrix;
    checked only because the file's own COMPAT_* macros claim to support
    it via the `#if __VERSION__ >= 130` branch — a structural check of that
    claim, not a target this project ships reconstruction features for)
  - GLSL 150 (desktop GL 3.2+)
  - GLSL 120 (older desktop GL, no `#if __VERSION__ >= 130` branch)

Usage: python3 tools/compile_gate/compile_check_legacy.py [file.glsl ...]
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TARGETS = list((REPO_ROOT / "shaders").glob("shaders_glsl/**/*.glsl"))

REQUIRED_TOOLS = ["glslangValidator"]

# (label, #version line, defines to prepend after it)
PROFILES = [
    ("GLES 300 (GLES3 mobile, the actual T-005 target)", "#version 300 es"),
    ("GLES 100 (structural check of the COMPAT_* GLES2 fallback only)", "#version 100"),
    ("GLSL 150 (desktop GL 3.2+)", "#version 150"),
    ("GLSL 120 (older desktop GL)", "#version 120"),
]


def check_tools() -> None:
    missing = [t for t in REQUIRED_TOOLS if shutil.which(t) is None]
    if missing:
        print(f"ERROR: required tools not on PATH: {', '.join(missing)}")
        sys.exit(2)


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def compile_stage(text: str, version_line: str, stage_define: str, stage_flag: str, tmpdir: Path, ext: str):
    src = tmpdir / f"stage.{ext}"
    src.write_text(f"{version_line}\n#define {stage_define}\n{text}\n")
    r = run(["glslangValidator", "-S", stage_flag, str(src)])
    return r


def check_file(path: Path) -> bool:
    text = path.read_text()
    ok = True
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        for label, version_line in PROFILES:
            for stage_define, stage_flag, ext in (("VERTEX", "vert", "vert"), ("FRAGMENT", "frag", "frag")):
                r = compile_stage(text, version_line, stage_define, stage_flag, tmpdir, ext)
                if r.returncode != 0:
                    print(f"FAIL {path} [{label}/{stage_define}]:\n{r.stdout}{r.stderr}")
                    ok = False
    if ok:
        labels = ", ".join(label for label, _ in PROFILES)
        print(f"PASS {path}: {labels} all compile clean (vertex + fragment)")
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
