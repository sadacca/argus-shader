"""Multi-pass RetroArch slang filter-chain sequencer — built for T-011's
comparison work. render_pass.py only handles single-pass presets (this
project's own shipped tiers); ScaleFX, xBRZ, and HQx (comparison baselines,
not this project's own shaders) are 3-6 pass chains with cross-pass texture
aliasing, which needed real sequencing rather than an improvised shortcut
(see docs/backlog-status.md's earlier note on why this wasn't attempted
before: "an unverified sequencer risks reporting misleading comparison
numbers, worse than not having them" — built carefully now, verified
against each preset's actual declared structure, not guessed).

Convention (confirmed against the real .slangp files this was built for —
see report.md): each pass declares a single `Source` sampler, bound to the
*previous* pass's rendered output (pass 0's Source is the true native input
image, matching render_pass.py's own single-pass convention). A pass that
declares `aliasN = some_name` makes its output additionally available,
under that exact name, to every later pass whose fragment shader declares a
same-named `uniform sampler2D` — RetroArch's own cross-pass aliasing
mechanism (e.g. ScaleFX's `scalefx-pass2.slang` samples `scalefx_pass0`
directly, skipping the intermediate pass). Declared `textures = ` preset
resources (e.g. HQx's `LUT`) are bound the same way: a fixed, non-aliased
extra texture, present for every pass whose shader declares that name.

Each pass renders into an FBO-attached texture (RGBA16F when the preset
sets `float_frameufferN = true`, matching passes that need to carry
out-of-[0,1]-range intermediate values — e.g. edge-direction encodings —
between passes without 8-bit quantization; RGBA8 otherwise) kept bound as
a live GL texture between passes rather than round-tripped through the
CPU, so only the final pass's output is ever read back.

Not a general-purpose filter-chain implementation: built and verified
against exactly the three real preset shapes this project needed (ScaleFX
6-pass, xBRZ 3-pass, HQx 5-pass+LUT). No `Original`/`OriginalHistory`/
feedback-pass support — none of these three presets use them, and this
project's own shipped shaders (which do eventually need `OriginalHistory`,
T-025) go through render_pass.py's single-pass path instead, per FR3.

Usage: python3 tools/render_harness/render_multipass.py preset.slangp source.png out.png --scale 4.0
"""
import argparse
import ctypes
import os
import re
import sys
from pathlib import Path

import numpy as np

# Must happen before the first `from OpenGL import ...` anywhere in the
# process — see render_pass.py's identical guard for why (PyOpenGL's
# platform-plugin choice, made on first import, decides whether its
# per-context state tracking can see a context made current via raw EGL
# ctypes calls). Duplicated rather than imported from render_pass because
# this file's own `from OpenGL import GL` below would otherwise run before
# render_pass.py's copy does, if something imports this module first.
os.environ.setdefault("PYOPENGL_PLATFORM", "egl")
from OpenGL import GL  # noqa: E402
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_pass import (compile_to_gles, compile_gl_shader, QUAD_POSITIONS, QUAD_TEXCOORDS,  # noqa: E402
                          parse_pragma_parameter_defaults, set_param_uniforms)
from egl_context import HeadlessContext  # noqa: E402

_KV_RE = re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"?([^"\r\n]*?)"?\s*$', re.MULTILINE)


def parse_preset(slangp_path: Path) -> dict:
    text = slangp_path.read_text()
    text = re.sub(r'#.*$', '', text, flags=re.MULTILINE)  # strip comment lines
    kv = {}
    for m in _KV_RE.finditer(text):
        key, val = m.group(1), m.group(2).strip()
        if val:
            kv[key] = val
    return kv


def preset_dir(slangp_path: Path) -> Path:
    return slangp_path.parent


def get_bool(kv: dict, key: str, default: bool = False) -> bool:
    return kv.get(key, str(default)).strip().lower() == "true"


def get_float(kv: dict, key: str, default: float) -> float:
    return float(kv[key]) if key in kv else default


_INCLUDE_RE = re.compile(r'^\s*#include\s+"([^"]+)"\s*$', re.MULTILINE)


def resolve_includes(slang_path: Path, tmpdir: Path) -> Path:
    """glslangValidator refuses `#include` without an explicit extension
    pragma real RetroArch's own slang preprocessor doesn't require (it
    resolves includes itself before compiling) — HQx's hq2x.slang needs
    this (`#include "pass2.inc"`). One-level, non-recursive text expansion
    is sufficient for what this project's fetched comparison shaders
    actually use; returns the original path unchanged if there's nothing
    to expand."""
    text = slang_path.read_text()
    if not _INCLUDE_RE.search(text):
        return slang_path
    def expand(m):
        return (slang_path.parent / m.group(1)).read_text()
    expanded = _INCLUDE_RE.sub(expand, text)
    out_path = tmpdir / slang_path.name
    out_path.write_text(expanded)
    return out_path


def link_program_from_slang(slang_path: Path, tmpdir: Path) -> int:
    slang_path = resolve_includes(slang_path, tmpdir)
    vert_src, frag_src = compile_to_gles(slang_path, tmpdir)
    vs = compile_gl_shader(vert_src, GL.GL_VERTEX_SHADER)
    fs = compile_gl_shader(frag_src, GL.GL_FRAGMENT_SHADER)
    prog = GL.glCreateProgram()
    GL.glAttachShader(prog, vs)
    GL.glAttachShader(prog, fs)
    GL.glLinkProgram(prog)
    if not GL.glGetProgramiv(prog, GL.GL_LINK_STATUS):
        log = GL.glGetProgramInfoLog(prog).decode(errors="replace")
        raise RuntimeError(f"link failed for {slang_path}:\n{log}")
    GL.glDeleteShader(vs)
    GL.glDeleteShader(fs)
    return prog


def make_input_texture(image_rgba: np.ndarray) -> int:
    tex = GL.glGenTextures(1)
    GL.glBindTexture(GL.GL_TEXTURE_2D, tex)
    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_NEAREST)
    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_NEAREST)
    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE)
    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)
    h, w = image_rgba.shape[:2]
    GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA8, w, h, 0, GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, image_rgba)
    return tex


def make_fbo_target(w: int, h: int, float_fb: bool):
    tex = GL.glGenTextures(1)
    GL.glBindTexture(GL.GL_TEXTURE_2D, tex)
    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_NEAREST)
    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_NEAREST)
    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE)
    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)
    if float_fb:
        GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA16F, w, h, 0, GL.GL_RGBA, GL.GL_FLOAT, None)
    else:
        GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA8, w, h, 0, GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, None)
    fbo = GL.glGenFramebuffers(1)
    GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, fbo)
    GL.glFramebufferTexture2D(GL.GL_FRAMEBUFFER, GL.GL_COLOR_ATTACHMENT0, GL.GL_TEXTURE_2D, tex, 0)
    status = GL.glCheckFramebufferStatus(GL.GL_FRAMEBUFFER)
    if status != GL.GL_FRAMEBUFFER_COMPLETE:
        raise RuntimeError(f"incomplete FBO (status {status:#x}), float_fb={float_fb}")
    return fbo, tex


def compute_pass_size(kv: dict, i: int, src_w: int, src_h: int, out_w: int, out_h: int):
    def axis(letter, prev_dim):
        st = kv.get(f"scale_type_{letter}{i}", kv.get(f"scale_type{i}", "source"))
        sc = get_float(kv, f"scale_{letter}{i}", get_float(kv, f"scale{i}", 1.0))
        if st == "viewport":
            return out_w if letter == "x" else out_h
        if st == "absolute":
            key = f"abs_{letter}{i}"
            return int(kv[key])
        return max(1, round(prev_dim * sc))  # "source": relative to this pass's own input
    return axis("x", src_w), axis("y", src_h)


def run_preset(slangp_path: Path, source_png: Path, out_scale: float, tmpdir: Path) -> np.ndarray:
    kv = parse_preset(slangp_path)
    base = preset_dir(slangp_path)
    n_shaders = int(kv["shaders"])

    src_img = np.array(Image.open(source_png).convert("RGBA"))
    src_h, src_w = src_img.shape[:2]
    out_w, out_h = int(src_w * out_scale), int(src_h * out_scale)

    textures = {}
    if "textures" in kv:
        for name in [t.strip() for t in kv["textures"].split(";") if t.strip()]:
            textures[name] = base / kv[name]

    with HeadlessContext(out_w, out_h):
        input_tex = make_input_texture(src_img)
        cur_w, cur_h = src_w, src_h
        cur_tex = input_tex
        aliased_outputs = {}  # name -> (texture, w, h)
        loaded_textures = {}  # name -> texture id (LUTs etc, loaded once)

        for i in range(n_shaders):
            shader_path = (base / kv[f"shader{i}"]).resolve()
            pass_tmpdir = tmpdir / f"pass{i}"
            pass_tmpdir.mkdir(exist_ok=True)
            prog = link_program_from_slang(shader_path, pass_tmpdir)
            GL.glUseProgram(prog)
            # Real RetroArch always initializes #pragma parameter uniforms to
            # their declared default (never leaves them at GL's implicit 0),
            # same reason render_pass.py's own T-020 fix needed this — found
            # here because ScaleFX's SFX_CLR (default 0.50) divides by
            # `params.SFX_CLR`, which is NaN-producing at the implicit 0.
            set_param_uniforms(prog, parse_pragma_parameter_defaults(shader_path))

            pass_w, pass_h = compute_pass_size(kv, i, cur_w, cur_h, out_w, out_h)
            float_fb = get_bool(kv, f"float_framebuffer{i}")
            fbo, out_tex = make_fbo_target(pass_w, pass_h, float_fb)
            GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, fbo)
            GL.glViewport(0, 0, pass_w, pass_h)

            mvp = np.identity(4, dtype=np.float32)
            if i < n_shaders - 1:
                # Every pass's fragment shader samples its "Source" (and any
                # alias) texture with a fixed quad that assumes a top-down
                # (PNG-convention) input — true only for the very first
                # pass's freshly-uploaded texture. A previous pass's own FBO
                # is stored bottom-up (GL's fixed rasterizer convention: clip
                # y=-1 always rasterizes to the render target's row 0), so
                # every non-final pass's OUTPUT would otherwise be handed to
                # the next pass upside down relative to what that pass
                # expects — and since each pass flips the convention again,
                # a chain's final orientation depended on its pass *count*
                # being even or odd, not on anything real (a genuine bug:
                # confirmed by the RPG dialogue box literally rendering
                # upside down through ScaleFX's 6-pass chain). Flipping Y
                # here for every pass except the last keeps every
                # intermediate FBO in the same top-down convention the next
                # pass already assumes, so only the final pass's own
                # readback (the existing, separately-correct np.flipud)
                # needs to correct for GL's bottom-up glReadPixels order —
                # exactly matching what already works for a single pass.
                mvp[1, 1] = -1.0
            source_size = np.array([cur_w, cur_h, 1.0 / cur_w, 1.0 / cur_h], dtype=np.float32)
            output_size = np.array([pass_w, pass_h, 1.0 / pass_w, 1.0 / pass_h], dtype=np.float32)
            ubo_data = np.concatenate([mvp.flatten(), source_size, output_size]).astype(np.float32)
            ubo = GL.glGenBuffers(1)
            GL.glBindBuffer(GL.GL_UNIFORM_BUFFER, ubo)
            GL.glBufferData(GL.GL_UNIFORM_BUFFER, ubo_data.nbytes, ubo_data, GL.GL_STATIC_DRAW)
            block_index = GL.glGetUniformBlockIndex(prog, "UBO")
            if block_index != GL.GL_INVALID_INDEX:
                GL.glUniformBlockBinding(prog, block_index, 0)
                GL.glBindBufferBase(GL.GL_UNIFORM_BUFFER, 0, ubo)

            # Push-constant style SourceSize/OriginalSize/OutputSize, best-effort
            # (T-018 convention) — the block's own *instance* name varies across
            # real third-party shaders (`params` in ScaleFX/xBRZ/SABR/bicubic,
            # `registers` in HQx; confirmed by grepping every vendored/fetched
            # pass this was built against), so both are tried; whichever the
            # given pass doesn't declare simply returns -1 and is skipped.
            for prefix in ("params", "registers"):
                for field_name, val in (("SourceSize", source_size), ("OriginalSize",
                        np.array([src_w, src_h, 1.0 / src_w, 1.0 / src_h], dtype=np.float32)),
                        ("OutputSize", output_size)):
                    loc = GL.glGetUniformLocation(prog, f"{prefix}.{field_name}")
                    if loc != -1:
                        GL.glUniform4f(loc, *val)

            unit = 0
            loc = GL.glGetUniformLocation(prog, "Source")
            if loc != -1:
                GL.glActiveTexture(GL.GL_TEXTURE0 + unit)
                GL.glBindTexture(GL.GL_TEXTURE_2D, cur_tex)
                GL.glUniform1i(loc, unit)
                unit += 1
            for name, (tex, _, _) in aliased_outputs.items():
                loc = GL.glGetUniformLocation(prog, name)
                if loc != -1:
                    GL.glActiveTexture(GL.GL_TEXTURE0 + unit)
                    GL.glBindTexture(GL.GL_TEXTURE_2D, tex)
                    GL.glUniform1i(loc, unit)
                    unit += 1
            for name, path in textures.items():
                loc = GL.glGetUniformLocation(prog, name)
                if loc != -1:
                    if name not in loaded_textures:
                        loaded_textures[name] = make_input_texture(np.array(Image.open(path).convert("RGBA")))
                    GL.glActiveTexture(GL.GL_TEXTURE0 + unit)
                    GL.glBindTexture(GL.GL_TEXTURE_2D, loaded_textures[name])
                    GL.glUniform1i(loc, unit)
                    unit += 1

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

            GL.glClearColor(0, 0, 0, 0)
            GL.glClear(GL.GL_COLOR_BUFFER_BIT)
            GL.glDrawArrays(GL.GL_TRIANGLE_STRIP, 0, 4)
            GL.glFinish()

            if f"alias{i}" in kv:
                aliased_outputs[kv[f"alias{i}"]] = (out_tex, pass_w, pass_h)

            cur_tex, cur_w, cur_h = out_tex, pass_w, pass_h
            cur_float = float_fb

        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, fbo)
        if cur_float:
            # A float-attached FBO can't be read back as GL_UNSIGNED_BYTE
            # (GL_INVALID_OPERATION) — read as GL_FLOAT and clamp/convert.
            pixels = GL.glReadPixels(0, 0, cur_w, cur_h, GL.GL_RGBA, GL.GL_FLOAT)
            out_f = np.frombuffer(pixels, dtype=np.float32).reshape(cur_h, cur_w, 4)
            out = np.clip(out_f, 0.0, 1.0)
            out = (out * 255.0 + 0.5).astype(np.uint8)
        else:
            pixels = GL.glReadPixels(0, 0, cur_w, cur_h, GL.GL_RGBA, GL.GL_UNSIGNED_BYTE)
            out = np.frombuffer(pixels, dtype=np.uint8).reshape(cur_h, cur_w, 4)
        return np.flipud(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("slangp_file", type=Path)
    ap.add_argument("source_png", type=Path)
    ap.add_argument("output_png", type=Path)
    ap.add_argument("--scale", type=float, default=1.0)
    args = ap.parse_args()

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        frame = run_preset(args.slangp_file, args.source_png, args.scale, Path(td))
    args.output_png.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(frame, mode="RGBA").save(args.output_png)
    print(f"wrote {args.output_png} ({frame.shape[1]}x{frame.shape[0]})")


if __name__ == "__main__":
    main()
