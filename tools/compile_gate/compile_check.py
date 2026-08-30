#!/usr/bin/env python3
"""T-002 cross-backend compile gate.

Splits a .slang file into its vertex/fragment stages (per the libretro slang
spec's #pragma stage markers), compiles each to SPIR-V with glslangValidator
(Vulkan semantics), validates the SPIR-V, then cross-compiles it with
spirv-cross to a representative shader source for each of the five backend
targets named in docs/requirements.md's Backend portability NFR:

  - Vulkan   -> SPIR-V itself (spirv-val is the correctness check)
  - GL       -> GLSL 150 (desktop, matches "GL 3.2+ unified slang driver")
  - GLES     -> ESSL 300 (mobile GL path, ties into T-005's GLES floor)
  - D3D11/12 -> HLSL shader model 5.0 (spirv-cross's hlsl backend targets
                one HLSL dialect; D3D11 and D3D12 both consume it, so one
                check stands in for both per the NFR's four-target list
                folding D3D10/11/12 together)
  - Metal    -> MSL

This does not link/run the shaders (no GPU in this environment — see
docs/backlog-status.md) and does not invoke vendor compilers (fxc/dxc,
metal) that aren't installed here; it verifies the parse + SPIR-V + SPIRV-Cross
translation pipeline, which is the portion that's actually available to run
in ordinary CI. Exit non-zero on any failure so it can gate a commit.

Usage: python3 tools/compile_gate/compile_check.py [file.slang ...]
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TARGETS = [REPO_ROOT / "tools" / "compile_gate" / "stub.slang"]

REQUIRED_TOOLS = ["glslangValidator", "spirv-val", "spirv-cross"]


def check_tools() -> None:
    missing = [t for t in REQUIRED_TOOLS if shutil.which(t) is None]
    if missing:
        print(f"ERROR: required tools not on PATH: {', '.join(missing)}")
        sys.exit(2)


def split_stages(text: str):
    """Return (prelude, vertex_body, fragment_body). Strips RetroArch-only
    #pragma directives (name/parameter/format/stage) that aren't real GLSL —
    RetroArch's own loader strips these before handing source to glslang, so
    the gate does the same to test what actually reaches the compiler."""
    lines = text.splitlines()
    prelude, vertex, fragment = [], [], []
    bucket = prelude
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#pragma stage vertex"):
            bucket = vertex
            continue
        if stripped.startswith("#pragma stage fragment"):
            bucket = fragment
            continue
        if re.match(r"^#pragma\s+(name|parameter|format)\b", stripped):
            continue
        bucket.append(line)
    return "\n".join(prelude), "\n".join(vertex), "\n".join(fragment)


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def compile_stage(prelude: str, body: str, stage: str, tmpdir: Path) -> Path:
    src = tmpdir / f"stage.{stage}"
    src.write_text(prelude + "\n" + body + "\n")
    spv = tmpdir / f"stage.{stage}.spv"
    stage_flag = {"vertex": "vert", "fragment": "frag"}[stage]
    r = run(["glslangValidator", "-V", "-S", stage_flag, "-o", str(spv), str(src)])
    if r.returncode != 0:
        raise RuntimeError(f"glslangValidator failed for {stage}:\n{r.stdout}\n{r.stderr}")
    return spv


def validate_spirv(spv: Path, stage: str):
    r = run(["spirv-val", str(spv)])
    if r.returncode != 0:
        raise RuntimeError(f"spirv-val failed for {stage} (Vulkan target):\n{r.stdout}\n{r.stderr}")


def cross_compile(spv: Path, stage: str, backend_name: str, args: list):
    r = run(["spirv-cross", str(spv)] + args)
    if r.returncode != 0:
        raise RuntimeError(f"spirv-cross failed for {stage} -> {backend_name}:\n{r.stdout}\n{r.stderr}")
    return r.stdout


BACKENDS = [
    ("GL (desktop, GLSL 150)", ["--version", "150"]),
    ("GLES (mobile, ESSL 300)", ["--version", "300", "--es"]),
    ("D3D11/D3D12 (HLSL SM 5.0)", ["--hlsl", "--shader-model", "50"]),
    ("Metal (MSL)", ["--msl"]),
]


def check_file(path: Path) -> bool:
    text = path.read_text()
    if not text.lstrip().startswith("#version"):
        print(f"FAIL {path}: file must start with #version (slang spec requirement)")
        return False

    prelude, vertex_body, fragment_body = split_stages(text)
    ok = True
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        try:
            vert_spv = compile_stage(prelude, vertex_body, "vertex", tmpdir)
            frag_spv = compile_stage(prelude, fragment_body, "fragment", tmpdir)
        except RuntimeError as e:
            print(f"FAIL {path}: {e}")
            return False

        for stage, spv in (("vertex", vert_spv), ("fragment", frag_spv)):
            try:
                validate_spirv(spv, stage)
            except RuntimeError as e:
                print(f"FAIL {path} [Vulkan/{stage}]: {e}")
                ok = False

        for backend_name, args in BACKENDS:
            for stage, spv in (("vertex", vert_spv), ("fragment", frag_spv)):
                try:
                    cross_compile(spv, stage, backend_name, args)
                except RuntimeError as e:
                    print(f"FAIL {path} [{backend_name}/{stage}]: {e}")
                    ok = False

    if ok:
        print(f"PASS {path}: Vulkan, GL, GLES, D3D11/12, Metal all compile clean")
    return ok


def main():
    check_tools()
    targets = [Path(a) for a in sys.argv[1:]] or DEFAULT_TARGETS
    results = [check_file(t) for t in targets]
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
