#version 330
/*
   T-040 — root legacy GLSL skeleton for the mobile-lite tier, counterpart to
   shaders_slang/argus/shaders/mobile-lite.slang (T-013). Independently
   authored per docs/licensing.md (T-001) — not derived from any reference
   shader's source. File structure (#if defined(VERTEX)/#elif
   defined(FRAGMENT) single-file conditional compilation, COMPAT_* macros,
   PARAMETER_UNIFORM convention) follows the documented libretro legacy GLSL
   shader driver spec (docs.libretro.com/development/shader/glsl-shaders/),
   confirmed against RetroArch's own gl_glsl_compile_shader() (gfx/
   drivers_shader/shader_glsl.c), which assembles the compiled source as
   [version][#define VERTEX|FRAGMENT + built-in defines][alias defines]
   [this file, verbatim] — no separate precision injection, so the default
   precision statement below is intentionally declared before any
   declaration that needs it (an ordering issue found and fixed while
   validating this file against a real driver: some upstream community
   shaders declare `out vec4 FragColor;` before their precision statement,
   which strict GLSL ES 3.00 frontends reject).

   T-045 finding, fixed here: the `#version 330` line above is not this
   file's actual compiled version — RetroArch's gl_glsl_compile_shader()
   strips it and substitutes its own, remapped from the number this file
   declares (source read directly from github.com/libretro/RetroArch
   gfx/drivers_shader/shader_glsl.c, `gl_glsl_compile_shader()`, 2026-09-19):
   on a GLES3-capable target, a declared version in [130, 330) remaps to
   "300 es", exactly 330 remaps to "310 es", and >330 remaps to "320 es";
   on desktop GL it's used verbatim. Declaring anything other than exactly
   330 here (e.g. the seemingly-more-conservative 130 the COMPAT_* macros
   below merely require) would silently cap this file at GLES "300 es" on
   real mobile hardware — one version short of the ES 3.10 this project's
   own T-005/docs/gles-floor.md floor requires for `bitCount()`, which the
   real reconstruction logic (once ported) needs. This file previously had
   no `#version` line at all, which is worse still: with no existing_version
   for the driver to find, no version is injected at all and the shader
   compiles under the GLSL ES 1.00 implicit default — incompatible with
   `texelFetch`/`in`/`out`/`bitCount` outright. See docs/backlog.md T-045 for
   the full investigation and why `tools/compile_gate/compile_check_legacy.py`'s
   current profile list does not yet test any of this correctly (it injects
   a version line externally, which is not how the real driver negotiates
   one once the file declares its own).

   Declares the FR5 tunables (docs/requirements.md); reconstruction logic is
   not implemented yet — passthrough for now. See mobile-lite.slang's header
   for the ticket sequence that fills this in.
*/

#pragma parameter ARGUS_EDGE_THRESHOLD "Edge Detection Threshold" 0.10 0.0 1.0 0.01
#pragma parameter ARGUS_DITHER_STRENGTH "Dither Preservation Strength" 1.0 0.0 1.0 0.05
#pragma parameter ARGUS_SHARPEN_AMOUNT "Sharpen Amount" 0.25 0.0 1.0 0.05
#pragma parameter ARGUS_TEMPORAL_BLEND "Temporal Blend Weight" 0.0 0.0 1.0 0.05

#if __VERSION__ >= 130
#define COMPAT_VARYING out
#define COMPAT_ATTRIBUTE in
#define COMPAT_TEXTURE texture
#else
#define COMPAT_VARYING varying
#define COMPAT_ATTRIBUTE attribute
#define COMPAT_TEXTURE texture2D
#endif

#ifdef GL_ES
#define COMPAT_PRECISION mediump
#else
#define COMPAT_PRECISION
#endif

/* GLSL ES fragment shaders have no default float precision — it must be
   declared before the first float-typed declaration that lacks an explicit
   qualifier. TEX0 below is shared by both stages (declared before the
   VERTEX/FRAGMENT branch), so a fragment-only precision statement inside
   the FRAGMENT branch (as most upstream examples place it) is too late:
   glslangValidator rejects it as "type requires declaration of default
   precision qualifier". Vertex shaders default to highp for float already,
   so this is a no-op there. */
#ifdef GL_ES
precision mediump float;
#endif

#ifdef PARAMETER_UNIFORM
uniform COMPAT_PRECISION float ARGUS_EDGE_THRESHOLD;
uniform COMPAT_PRECISION float ARGUS_DITHER_STRENGTH;
uniform COMPAT_PRECISION float ARGUS_SHARPEN_AMOUNT;
uniform COMPAT_PRECISION float ARGUS_TEMPORAL_BLEND;
#else
#define ARGUS_EDGE_THRESHOLD 0.10
#define ARGUS_DITHER_STRENGTH 1.0
#define ARGUS_SHARPEN_AMOUNT 0.25
#define ARGUS_TEMPORAL_BLEND 0.0
#endif

COMPAT_VARYING vec2 TEX0;

#if defined(VERTEX)

COMPAT_ATTRIBUTE vec4 VertexCoord;
COMPAT_ATTRIBUTE vec4 TexCoord;
uniform mat4 MVPMatrix;

void main()
{
   gl_Position = MVPMatrix * VertexCoord;
   TEX0 = TexCoord.xy;
}

#elif defined(FRAGMENT)

#ifdef GL_ES
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif
#endif

#if __VERSION__ >= 130
out vec4 FragColor;
#else
#define FragColor gl_FragColor
#endif

uniform sampler2D Texture;

void main()
{
   FragColor = COMPAT_TEXTURE(Texture, TEX0);
}

#endif
