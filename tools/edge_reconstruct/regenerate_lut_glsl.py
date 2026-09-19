#!/usr/bin/env python3
"""T-018 — regenerate edge_debug.slang's embedded topology-LUT constant array
from tools/lut/generate_lut.py's edge_geometry(), the same source of truth
T-014's baked topology_lut.png/.bin use.

Why this shader embeds the LUT as a GLSL `const vec3[256]` array instead of
sampling T-014's baked texture the way T-014's own acceptance criterion
describes (and the way this project's shipped shader should still do it):
this environment's Mesa/llvmpipe software rasterizer has a real,
reproducible miscompilation when a *second* texture sampler (beyond
`Source`) is read with a dynamically-computed (non-constant) `texelFetch`
index — isolated to a minimal repro in `report.md` Finding 1. A
dynamically-indexed local *array* is not affected (this project's
classifier shaders already dynamically index local arrays without issue);
only a second dynamically-indexed *sampler* is. Swapping the LUT lookup from
`texelFetch(TopologyLUT, ivec2(idx, 0), 0)` to `TOPOLOGY_LUT[idx]` sidesteps
the bug entirely while testing the exact same 256 entries — this only
affects how this pre-fusion *debug/verification* shader is allowed to run
against this environment's software rasterizer, not T-018's actual designed
rule or T-014's texture-based design for the real shipped pass (T-020),
which should be re-tested against a real GPU driver before assuming the
texture path is safe there too.

Usage: python3 tools/edge_reconstruct/regenerate_lut_glsl.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lut"))
from generate_lut import edge_geometry  # noqa: E402

BEGIN = "// BEGIN GENERATED TOPOLOGY LUT (tools/edge_reconstruct/regenerate_lut_glsl.py) ---"
END = "// END GENERATED TOPOLOGY LUT ---"

SHADER_PATH = Path(__file__).resolve().parent / "edge_debug.slang"


def build_array_glsl() -> str:
    entries = [edge_geometry(i) for i in range(256)]
    lines = [f"   vec3({dx:.6f}, {dy:.6f}, {conf:.6f})" for dx, dy, conf in entries]
    body = ",\n".join(lines)
    return f"{BEGIN}\nconst vec3 TOPOLOGY_LUT[256] = vec3[256](\n{body}\n);\n{END}"


def main():
    text = SHADER_PATH.read_text()
    start = text.index(BEGIN)
    end = text.index(END) + len(END)
    new_text = text[:start] + build_array_glsl() + text[end:]
    SHADER_PATH.write_text(new_text)
    print(f"regenerated {SHADER_PATH}")


if __name__ == "__main__":
    main()
