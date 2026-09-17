"""T-003 — render a single .slang pass against a source PNG and dump the
output frame.

Feeds the *same* GLES cross-compile that T-002's compile gate already
validates (glslangValidator -> SPIR-V -> spirv-cross --es) through an actual
GLES 3.0 context (see egl_context.py), rather than a second, independent
GLSL implementation — so this checks what RetroArch's GLES backend would
actually run, not a hand-maintained approximation of it.

Only single-pass, source-resolution-in/viewport-resolution-out presets are
handled (sufficient for the mobile-lite tier, T-013/T-040's only shipped
preset so far); multi-pass filter-chain sequencing is out of scope until a
multi-pass tier needs it.
"""
import argparse
import ctypes
import hashlib
import sys
from pathlib import Path

import numpy as np
from OpenGL import GL
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools" / "compile_gate"))
from compile_check import split_stages, run as run_cmd  # noqa: E402

from egl_context import HeadlessContext  # noqa: E402

# Fullscreen quad in RetroArch's vertex convention: clip-space position +
# [0,1] texcoords, drawn as a triangle strip.
QUAD_POSITIONS = np.array(
    [-1, -1, 0, 1, 1, -1, 0, 1, -1, 1, 0, 1, 1, 1, 0, 1], dtype=np.float32
)
QUAD_TEXCOORDS = np.array([0, 1, 1, 1, 0, 0, 1, 0], dtype=np.float32)


def compile_to_gles(slang_path: Path, tmpdir: Path):
    text = slang_path.read_text()
    prelude, vert_body, frag_body = split_stages(text)
    results = {}
    for stage, body, stage_flag in (
        ("vertex", vert_body, "vert"),
        ("fragment", frag_body, "frag"),
    ):
        src = tmpdir / f"stage.{stage}"
        src.write_text(prelude + "\n" + body + "\n")
        spv = tmpdir / f"stage.{stage}.spv"
        r = run_cmd(["glslangValidator", "-V", "-S", stage_flag, "-o", str(spv), str(src)])
        if r.returncode != 0:
            raise RuntimeError(f"glslangValidator failed for {stage}:\n{r.stdout}{r.stderr}")
        # 310, not 300: matches docs/gles-floor.md's (T-005) actual decided
        # floor of GLES 3.1+ core, gather-only, no GLES 3.0 fallback — and
        # this environment's real context negotiates ES 3.2 (confirmed via
        # GL_SHADING_LANGUAGE_VERSION), so 310 is also what's actually
        # being exercised, not an aspirational target.
        r = run_cmd(["spirv-cross", str(spv), "--version", "310", "--es"])
        if r.returncode != 0:
            raise RuntimeError(f"spirv-cross failed for {stage}:\n{r.stdout}{r.stderr}")
        results[stage] = r.stdout
    return results["vertex"], results["fragment"]


def compile_gl_shader(source: str, stage: int) -> int:
    shader = GL.glCreateShader(stage)
    GL.glShaderSource(shader, source)
    GL.glCompileShader(shader)
    if not GL.glGetShaderiv(shader, GL.GL_COMPILE_STATUS):
        log = GL.glGetShaderInfoLog(shader).decode(errors="replace")
        raise RuntimeError(f"GL shader compile failed:\n{log}\n--- source ---\n{source}")
    return shader


def link_program(vert_src: str, frag_src: str) -> int:
    vs = compile_gl_shader(vert_src, GL.GL_VERTEX_SHADER)
    fs = compile_gl_shader(frag_src, GL.GL_FRAGMENT_SHADER)
    prog = GL.glCreateProgram()
    GL.glAttachShader(prog, vs)
    GL.glAttachShader(prog, fs)
    GL.glLinkProgram(prog)
    if not GL.glGetProgramiv(prog, GL.GL_LINK_STATUS):
        log = GL.glGetProgramInfoLog(prog).decode(errors="replace")
        raise RuntimeError(f"GL program link failed:\n{log}")
    GL.glDeleteShader(vs)
    GL.glDeleteShader(fs)
    return prog


def set_param_uniforms(prog: int, params: dict):
    """Best-effort: only sets uniforms that exist (passthrough skeletons
    declare the FR5 params but don't read them yet, so most are absent —
    GL_INVALID_OPERATION on a -1 location is silently avoided instead of
    treated as an error, since RetroArch's own loader does the same)."""
    for name, value in params.items():
        loc = GL.glGetUniformLocation(prog, f"params.{name}")
        if loc != -1:
            GL.glUniform1f(loc, value)


def set_standard_push_constants(prog: int, src_w: int, src_h: int, out_w: int, out_h: int):
    """T-018 addition: many single-pass libretro slang shaders (this
    project's own passes among them use a UBO instead, but third-party
    comparison shaders like Omniscale commonly don't) put SourceSize/
    OriginalSize/OutputSize/FrameCount in the push-constant block instead of
    the UBO. spirv-cross's GLES output flattens that into a plain
    `uniform Push params` struct addressable the same way as this project's
    own FR5 params (`params.<field>`), so this is a best-effort set of the
    same four fields RetroArch's own filter-chain always provides, purely
    additive: a no-op for this project's own shaders, which don't declare
    push-constant fields with these names."""
    source_size = (float(src_w), float(src_h), 1.0 / src_w, 1.0 / src_h)
    output_size = (float(out_w), float(out_h), 1.0 / out_w, 1.0 / out_h)
    for field_name, value in (
        ("SourceSize", source_size),
        ("OriginalSize", source_size),  # no prior filter-chain pass in this harness — same as Source
        ("OutputSize", output_size),
    ):
        loc = GL.glGetUniformLocation(prog, f"params.{field_name}")
        if loc != -1:
            GL.glUniform4f(loc, *value)
    loc = GL.glGetUniformLocation(prog, "params.FrameCount")
    if loc != -1:
        GL.glUniform1ui(loc, 0)


def make_texture(image: np.ndarray) -> int:
    tex = GL.glGenTextures(1)
    GL.glBindTexture(GL.GL_TEXTURE_2D, tex)
    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_NEAREST)
    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_NEAREST)
    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE)
    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)
    h, w = image.shape[:2]
    GL.glTexImage2D(
        GL.GL_TEXTURE_2D, 0, GL.GL_RGBA8, w, h, 0, GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, image
    )
    return tex


def render_pass(slang_path: Path, source_png: Path, scale: float, tmpdir: Path, params: dict,
                 extra_textures: dict = None):
    """extra_textures: optional {sampler_uniform_name: png_path} for shaders
    that read a second static texture besides Source (T-018 addition: LUT
    textures aren't part of any preset this harness handled before). Bound
    starting at texture unit 1, nearest-filtered, clamp-to-edge — same
    convention as Source and as tools/lut/generate_lut.py's own stated
    consumption model (`texelFetch`, no interpolation)."""
    src_img = np.array(Image.open(source_png).convert("RGBA"))
    src_h, src_w = src_img.shape[:2]
    out_w, out_h = int(src_w * scale), int(src_h * scale)

    with HeadlessContext(out_w, out_h):
        vert_src, frag_src = compile_to_gles(slang_path, tmpdir)
        prog = link_program(vert_src, frag_src)
        GL.glUseProgram(prog)

        # UBO: MVP identity, SourceSize/OutputSize per the slang spec (xy =
        # size, zw = 1/size), std140-packed as mat4 + vec4 + vec4.
        mvp = np.identity(4, dtype=np.float32)
        source_size = np.array([src_w, src_h, 1.0 / src_w, 1.0 / src_h], dtype=np.float32)
        output_size = np.array([out_w, out_h, 1.0 / out_w, 1.0 / out_h], dtype=np.float32)
        ubo_data = np.concatenate([mvp.flatten(), source_size, output_size]).astype(np.float32)

        ubo = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_UNIFORM_BUFFER, ubo)
        GL.glBufferData(GL.GL_UNIFORM_BUFFER, ubo_data.nbytes, ubo_data, GL.GL_STATIC_DRAW)
        block_index = GL.glGetUniformBlockIndex(prog, "UBO")
        if block_index != GL.GL_INVALID_INDEX:
            GL.glUniformBlockBinding(prog, block_index, 0)
            GL.glBindBufferBase(GL.GL_UNIFORM_BUFFER, 0, ubo)

        set_param_uniforms(prog, params)
        set_standard_push_constants(prog, src_w, src_h, out_w, out_h)

        tex = make_texture(src_img)
        sampler_loc = GL.glGetUniformLocation(prog, "Source")
        if sampler_loc != -1:
            GL.glActiveTexture(GL.GL_TEXTURE0)
            GL.glBindTexture(GL.GL_TEXTURE_2D, tex)
            GL.glUniform1i(sampler_loc, 0)

        for unit, (name, tex_png) in enumerate((extra_textures or {}).items(), start=1):
            extra_loc = GL.glGetUniformLocation(prog, name)
            if extra_loc != -1:
                extra_img = np.array(Image.open(tex_png).convert("RGBA"))
                extra_tex = make_texture(extra_img)
                GL.glActiveTexture(GL.GL_TEXTURE0 + unit)
                GL.glBindTexture(GL.GL_TEXTURE_2D, extra_tex)
                GL.glUniform1i(extra_loc, unit)

        pos_vbo = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, pos_vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, QUAD_POSITIONS.nbytes, QUAD_POSITIONS, GL.GL_STATIC_DRAW)
        pos_loc = GL.glGetAttribLocation(prog, "Position")
        if pos_loc != -1:
            GL.glEnableVertexAttribArray(pos_loc)
            GL.glVertexAttribPointer(pos_loc, 4, GL.GL_FLOAT, GL.GL_FALSE, 0, ctypes.c_void_p(0))

        tex_vbo = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, tex_vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, QUAD_TEXCOORDS.nbytes, QUAD_TEXCOORDS, GL.GL_STATIC_DRAW)
        tex_loc = GL.glGetAttribLocation(prog, "TexCoord")
        if tex_loc != -1:
            GL.glEnableVertexAttribArray(tex_loc)
            GL.glVertexAttribPointer(tex_loc, 2, GL.GL_FLOAT, GL.GL_FALSE, 0, ctypes.c_void_p(0))

        GL.glViewport(0, 0, out_w, out_h)
        GL.glClearColor(0, 0, 0, 0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)
        GL.glDrawArrays(GL.GL_TRIANGLE_STRIP, 0, 4)
        GL.glFinish()

        pixels = GL.glReadPixels(0, 0, out_w, out_h, GL.GL_RGBA, GL.GL_UNSIGNED_BYTE)
        out = np.frombuffer(pixels, dtype=np.uint8).reshape(out_h, out_w, 4)
        out = np.flipud(out)  # GL's origin is bottom-left; PNG's is top-left
        return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("slang_file", type=Path)
    ap.add_argument("source_png", type=Path)
    ap.add_argument("output_png", type=Path)
    ap.add_argument("--scale", type=float, default=1.0, help="output/source resolution ratio")
    ap.add_argument("--check-determinism", action="store_true",
                     help="render twice and fail unless byte-identical (T-003 acceptance)")
    args = ap.parse_args()

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        frame1 = render_pass(args.slang_file, args.source_png, args.scale, tmpdir, {})
        if args.check_determinism:
            frame2 = render_pass(args.slang_file, args.source_png, args.scale, tmpdir, {})
            h1 = hashlib.sha256(frame1.tobytes()).hexdigest()
            h2 = hashlib.sha256(frame2.tobytes()).hexdigest()
            if h1 != h2:
                print(f"FAIL determinism: run1={h1} run2={h2}")
                sys.exit(1)
            print(f"PASS determinism: {h1}")

    args.output_png.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(frame1, mode="RGBA").save(args.output_png)
    print(f"wrote {args.output_png} ({frame1.shape[1]}x{frame1.shape[0]})")


if __name__ == "__main__":
    main()
