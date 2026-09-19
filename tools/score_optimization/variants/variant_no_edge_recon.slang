#version 450

// T-020 — fused mobile-lite pass. Combines T-016's four-class region
// classifier with T-017/T-018/T-019's three per-class reconstruction rules
// into the single shipped pass FR3 requires (1 pass, 1 output-resolution
// pass, zero intermediate render targets — this file *is* that one pass).
//
// Each block below is a direct port of its already-verified debug shader
// (tools/classifier_gpu/classify_debug.slang, tools/dither_reconstruct/
// dither_debug.slang, tools/text_protect/text_debug.slang,
// tools/edge_reconstruct/edge_debug.slang) — the classification statistics,
// thresholds, and per-class rules are unchanged from what each ticket's own
// verify_gpu.py already checked against a CPU reference through the real
// GLES render path; this file's job is only to fuse them, not to re-derive
// any of the math. See tools/fusion/report.md for the fusion-specific
// verification (each class's shipped output matches its own debug shader's
// output on content dominated by that class) and known gaps.
//
// FR5's ARGUS_SHARPEN_AMOUNT and ARGUS_TEMPORAL_BLEND remain declared but
// unused, same as T-013's original skeleton: no Phase 1 ticket assigns
// their implementation (temporal stability is T-025, Phase 2; a dedicated
// sharpen pass isn't scoped to any ticket yet) — declaring them now means
// presets/configs that reference them don't need to change when they are.
//
// The topology LUT is embedded as a generated constant array rather than
// sampled from T-014's baked texture, for the same reason
// tools/edge_reconstruct/edge_debug.slang is: this environment's Mesa/
// llvmpipe software rasterizer has a real, reproducible miscompilation with
// a dynamically-indexed texelFetch on a second sampler (see
// tools/edge_reconstruct/report.md Finding 1). This is the actual shipped
// pass, not just a debug shader, so this deviation from T-014's stated
// texture-sampling design matters more here — tracked as open follow-up
// work (see tools/fusion/report.md) to re-verify the texture path on real
// GPU hardware and switch back if it's safe there, rather than carrying a
// software-rasterizer workaround into a real release without re-checking it.
//
// textureGather (T-005: this project's device matrix supports gather-only,
// no GLES 3.0 fallback needed) is NOT used here — every neighbor tap is an
// individual texelFetch, matching what was already verified in each
// contributing debug shader. Adopting textureGather to reduce fetch-
// instruction count is a real, tracked performance optimization (see
// tools/fusion/report.md), not attempted here since it changes the fetch
// pattern in a way that would need its own from-scratch verification, and
// this project's actual bandwidth/frame-time numbers (T-021, T-022) are
// still blocked on real handheld hardware regardless (T-006).

layout(set = 0, binding = 0, std140) uniform UBO
{
   mat4 MVP;
   vec4 SourceSize;
   vec4 OutputSize;
} global;

#pragma name ArgusMobileLite

#pragma parameter ARGUS_EDGE_THRESHOLD "Edge Detection Threshold" 0.10 0.0 1.0 0.01
#pragma parameter ARGUS_DITHER_STRENGTH "Dither Preservation Strength" 1.0 0.0 1.0 0.05
#pragma parameter ARGUS_SHARPEN_AMOUNT "Sharpen Amount" 0.25 0.0 1.0 0.05
#pragma parameter ARGUS_TEMPORAL_BLEND "Temporal Blend Weight" 0.0 0.0 1.0 0.05

layout(push_constant) uniform Push
{
   float ARGUS_EDGE_THRESHOLD;
   float ARGUS_DITHER_STRENGTH;
   float ARGUS_SHARPEN_AMOUNT;
   float ARGUS_TEMPORAL_BLEND;
} params;

#pragma stage vertex
layout(location = 0) in vec4 Position;
layout(location = 1) in vec2 TexCoord;
layout(location = 0) out vec2 vTexCoord;
void main()
{
   gl_Position = global.MVP * Position;
   vTexCoord = TexCoord;
}

#pragma stage fragment
layout(location = 0) in vec2 vTexCoord;
layout(location = 0) out vec4 FragColor;
layout(binding = 1) uniform sampler2D Source;

// --- shared classification thresholds (T-015/T-016) ---
const highp float CHECKERBOARD_HI = 0.15;
const highp float POPCOUNT_DITHER_MAX = 2.0;
const highp float VARIANCE_FLAT_MAX = 20.0;
const highp float STROKE_WIDTH_MAX = 2.0;
const highp float MIN_SPREAD = 0.5;

// --- T-019 dither-preservation constant ---
const highp float SPREAD_HARD_REF = 20.0;

highp float luma(vec3 c)
{
   return dot(c, vec3(0.299, 0.587, 0.114)) * 255.0;
}

// BEGIN GENERATED TOPOLOGY LUT (tools/edge_reconstruct/regenerate_lut_glsl.py) ---
const vec3 TOPOLOGY_LUT[256] = vec3[256](
   vec3(0.000000, 0.000000, 0.000000),
   vec3(0.000000, -1.000000, 0.125000),
   vec3(0.707107, -0.707107, 0.125000),
   vec3(0.382683, -0.923880, 0.250000),
   vec3(1.000000, -0.000000, 0.125000),
   vec3(0.707107, -0.707107, 0.250000),
   vec3(0.923880, -0.382683, 0.250000),
   vec3(0.707107, -0.707107, 0.375000),
   vec3(0.707107, 0.707107, 0.125000),
   vec3(0.923880, -0.382683, 0.250000),
   vec3(1.000000, -0.000000, 0.250000),
   vec3(0.816497, -0.577350, 0.375000),
   vec3(0.923880, 0.382683, 0.250000),
   vec3(0.985599, -0.169102, 0.375000),
   vec3(1.000000, -0.000000, 0.375000),
   vec3(0.923880, -0.382683, 0.500000),
   vec3(0.000000, 1.000000, 0.125000),
   vec3(0.000000, 0.000000, 0.250000),
   vec3(0.923880, 0.382683, 0.250000),
   vec3(0.707107, -0.707107, 0.375000),
   vec3(0.707107, 0.707107, 0.250000),
   vec3(1.000000, 0.000000, 0.375000),
   vec3(0.985599, 0.169102, 0.375000),
   vec3(0.923880, -0.382683, 0.500000),
   vec3(0.382683, 0.923880, 0.250000),
   vec3(0.707107, 0.707107, 0.375000),
   vec3(0.816497, 0.577350, 0.375000),
   vec3(1.000000, 0.000000, 0.500000),
   vec3(0.707107, 0.707107, 0.375000),
   vec3(0.923880, 0.382683, 0.500000),
   vec3(0.923880, 0.382683, 0.500000),
   vec3(1.000000, 0.000000, 0.625000),
   vec3(-0.707107, 0.707107, 0.125000),
   vec3(-0.923880, -0.382683, 0.250000),
   vec3(0.000000, 0.000000, 0.250000),
   vec3(0.000000, -1.000000, 0.375000),
   vec3(0.382683, 0.923880, 0.250000),
   vec3(0.707107, -0.707107, 0.375000),
   vec3(1.000000, 0.000000, 0.375000),
   vec3(0.707107, -0.707107, 0.500000),
   vec3(0.000000, 1.000000, 0.250000),
   vec3(0.000000, 1.000000, 0.375000),
   vec3(0.707107, 0.707107, 0.375000),
   vec3(0.923880, -0.382683, 0.500000),
   vec3(0.577350, 0.816497, 0.375000),
   vec3(0.923880, 0.382683, 0.500000),
   vec3(0.923880, 0.382683, 0.500000),
   vec3(0.985599, -0.169102, 0.625000),
   vec3(-0.382683, 0.923880, 0.250000),
   vec3(-0.707107, 0.707107, 0.375000),
   vec3(0.000000, 1.000000, 0.375000),
   vec3(0.000000, 0.000000, 0.500000),
   vec3(0.169102, 0.985599, 0.375000),
   vec3(0.382683, 0.923880, 0.500000),
   vec3(0.707107, 0.707107, 0.500000),
   vec3(1.000000, 0.000000, 0.625000),
   vec3(0.000000, 1.000000, 0.375000),
   vec3(0.000000, 1.000000, 0.500000),
   vec3(0.382683, 0.923880, 0.500000),
   vec3(0.707107, 0.707107, 0.625000),
   vec3(0.382683, 0.923880, 0.500000),
   vec3(0.577350, 0.816497, 0.625000),
   vec3(0.707107, 0.707107, 0.625000),
   vec3(0.923880, 0.382683, 0.750000),
   vec3(-1.000000, 0.000000, 0.125000),
   vec3(-0.707107, -0.707107, 0.250000),
   vec3(-0.382683, -0.923880, 0.250000),
   vec3(-0.169102, -0.985599, 0.375000),
   vec3(0.000000, 0.000000, 0.250000),
   vec3(0.000000, -1.000000, 0.375000),
   vec3(0.707107, -0.707107, 0.375000),
   vec3(0.382683, -0.923880, 0.500000),
   vec3(-0.382683, 0.923880, 0.250000),
   vec3(-0.707107, -0.707107, 0.375000),
   vec3(1.000000, 0.000000, 0.375000),
   vec3(0.382683, -0.923880, 0.500000),
   vec3(0.707107, 0.707107, 0.375000),
   vec3(0.923880, -0.382683, 0.500000),
   vec3(1.000000, -0.000000, 0.500000),
   vec3(0.816497, -0.577350, 0.625000),
   vec3(-0.707107, 0.707107, 0.250000),
   vec3(-1.000000, 0.000000, 0.375000),
   vec3(-0.707107, 0.707107, 0.375000),
   vec3(-0.382683, -0.923880, 0.500000),
   vec3(0.000000, 1.000000, 0.375000),
   vec3(0.000000, 0.000000, 0.500000),
   vec3(0.923880, 0.382683, 0.500000),
   vec3(0.707107, -0.707107, 0.625000),
   vec3(-0.169102, 0.985599, 0.375000),
   vec3(-0.382683, 0.923880, 0.500000),
   vec3(0.382683, 0.923880, 0.500000),
   vec3(1.000000, 0.000000, 0.625000),
   vec3(0.382683, 0.923880, 0.500000),
   vec3(0.707107, 0.707107, 0.625000),
   vec3(0.816497, 0.577350, 0.625000),
   vec3(1.000000, 0.000000, 0.750000),
   vec3(-0.923880, 0.382683, 0.250000),
   vec3(-0.985599, -0.169102, 0.375000),
   vec3(-1.000000, 0.000000, 0.375000),
   vec3(-0.707107, -0.707107, 0.500000),
   vec3(-0.707107, 0.707107, 0.375000),
   vec3(-0.923880, -0.382683, 0.500000),
   vec3(0.000000, 0.000000, 0.500000),
   vec3(0.000000, -1.000000, 0.625000),
   vec3(-0.577350, 0.816497, 0.375000),
   vec3(-0.923880, 0.382683, 0.500000),
   vec3(-0.382683, 0.923880, 0.500000),
   vec3(-0.707107, -0.707107, 0.625000),
   vec3(0.000000, 1.000000, 0.500000),
   vec3(0.000000, 1.000000, 0.625000),
   vec3(0.707107, 0.707107, 0.625000),
   vec3(0.923880, -0.382683, 0.750000),
   vec3(-0.707107, 0.707107, 0.375000),
   vec3(-0.923880, 0.382683, 0.500000),
   vec3(-0.707107, 0.707107, 0.500000),
   vec3(-1.000000, 0.000000, 0.625000),
   vec3(-0.382683, 0.923880, 0.500000),
   vec3(-0.707107, 0.707107, 0.625000),
   vec3(0.000000, 1.000000, 0.625000),
   vec3(0.000000, 0.000000, 0.750000),
   vec3(-0.382683, 0.923880, 0.500000),
   vec3(-0.577350, 0.816497, 0.625000),
   vec3(-0.169102, 0.985599, 0.625000),
   vec3(-0.382683, 0.923880, 0.750000),
   vec3(0.000000, 1.000000, 0.625000),
   vec3(0.000000, 1.000000, 0.750000),
   vec3(0.382683, 0.923880, 0.750000),
   vec3(0.707107, 0.707107, 0.875000),
   vec3(-0.707107, -0.707107, 0.125000),
   vec3(-0.382683, -0.923880, 0.250000),
   vec3(-0.000000, -1.000000, 0.250000),
   vec3(-0.000000, -1.000000, 0.375000),
   vec3(0.382683, -0.923880, 0.250000),
   vec3(0.169102, -0.985599, 0.375000),
   vec3(0.577350, -0.816497, 0.375000),
   vec3(0.382683, -0.923880, 0.500000),
   vec3(0.000000, 0.000000, 0.250000),
   vec3(-0.000000, -1.000000, 0.375000),
   vec3(0.707107, -0.707107, 0.375000),
   vec3(0.382683, -0.923880, 0.500000),
   vec3(1.000000, 0.000000, 0.375000),
   vec3(0.707107, -0.707107, 0.500000),
   vec3(0.923880, -0.382683, 0.500000),
   vec3(0.707107, -0.707107, 0.625000),
   vec3(-0.923880, 0.382683, 0.250000),
   vec3(-0.707107, -0.707107, 0.375000),
   vec3(-0.000000, -1.000000, 0.375000),
   vec3(-0.000000, -1.000000, 0.500000),
   vec3(0.707107, 0.707107, 0.375000),
   vec3(0.382683, -0.923880, 0.500000),
   vec3(0.923880, -0.382683, 0.500000),
   vec3(0.577350, -0.816497, 0.625000),
   vec3(0.000000, 1.000000, 0.375000),
   vec3(0.000000, 0.000000, 0.500000),
   vec3(0.923880, 0.382683, 0.500000),
   vec3(0.707107, -0.707107, 0.625000),
   vec3(0.707107, 0.707107, 0.500000),
   vec3(1.000000, 0.000000, 0.625000),
   vec3(0.985599, 0.169102, 0.625000),
   vec3(0.923880, -0.382683, 0.750000),
   vec3(-1.000000, 0.000000, 0.250000),
   vec3(-0.816497, -0.577350, 0.375000),
   vec3(-0.707107, -0.707107, 0.375000),
   vec3(-0.382683, -0.923880, 0.500000),
   vec3(-1.000000, 0.000000, 0.375000),
   vec3(-0.382683, -0.923880, 0.500000),
   vec3(0.382683, -0.923880, 0.500000),
   vec3(0.169102, -0.985599, 0.625000),
   vec3(-0.707107, 0.707107, 0.375000),
   vec3(-0.923880, -0.382683, 0.500000),
   vec3(0.000000, 0.000000, 0.500000),
   vec3(-0.000000, -1.000000, 0.625000),
   vec3(0.382683, 0.923880, 0.500000),
   vec3(0.707107, -0.707107, 0.625000),
   vec3(1.000000, 0.000000, 0.625000),
   vec3(0.707107, -0.707107, 0.750000),
   vec3(-0.816497, 0.577350, 0.375000),
   vec3(-1.000000, 0.000000, 0.500000),
   vec3(-0.923880, 0.382683, 0.500000),
   vec3(-0.707107, -0.707107, 0.625000),
   vec3(-0.382683, 0.923880, 0.500000),
   vec3(-1.000000, 0.000000, 0.625000),
   vec3(0.707107, 0.707107, 0.625000),
   vec3(0.382683, -0.923880, 0.750000),
   vec3(-0.382683, 0.923880, 0.500000),
   vec3(-0.707107, 0.707107, 0.625000),
   vec3(0.000000, 1.000000, 0.625000),
   vec3(0.000000, 0.000000, 0.750000),
   vec3(0.169102, 0.985599, 0.625000),
   vec3(0.382683, 0.923880, 0.750000),
   vec3(0.707107, 0.707107, 0.750000),
   vec3(1.000000, 0.000000, 0.875000),
   vec3(-0.923880, -0.382683, 0.250000),
   vec3(-0.707107, -0.707107, 0.375000),
   vec3(-0.577350, -0.816497, 0.375000),
   vec3(-0.382683, -0.923880, 0.500000),
   vec3(-0.707107, -0.707107, 0.375000),
   vec3(-0.382683, -0.923880, 0.500000),
   vec3(-0.000000, -1.000000, 0.500000),
   vec3(-0.000000, -1.000000, 0.625000),
   vec3(-1.000000, 0.000000, 0.375000),
   vec3(-0.707107, -0.707107, 0.500000),
   vec3(-0.382683, -0.923880, 0.500000),
   vec3(-0.169102, -0.985599, 0.625000),
   vec3(0.000000, 0.000000, 0.500000),
   vec3(-0.000000, -1.000000, 0.625000),
   vec3(0.707107, -0.707107, 0.625000),
   vec3(0.382683, -0.923880, 0.750000),
   vec3(-0.985599, 0.169102, 0.375000),
   vec3(-0.923880, -0.382683, 0.500000),
   vec3(-0.923880, -0.382683, 0.500000),
   vec3(-0.577350, -0.816497, 0.625000),
   vec3(-0.923880, 0.382683, 0.500000),
   vec3(-0.707107, -0.707107, 0.625000),
   vec3(0.000000, -1.000000, 0.625000),
   vec3(0.000000, -1.000000, 0.750000),
   vec3(-0.707107, 0.707107, 0.500000),
   vec3(-1.000000, 0.000000, 0.625000),
   vec3(-0.707107, 0.707107, 0.625000),
   vec3(-0.382683, -0.923880, 0.750000),
   vec3(0.000000, 1.000000, 0.625000),
   vec3(0.000000, 0.000000, 0.750000),
   vec3(0.923880, 0.382683, 0.750000),
   vec3(0.707107, -0.707107, 0.875000),
   vec3(-1.000000, 0.000000, 0.375000),
   vec3(-0.923880, -0.382683, 0.500000),
   vec3(-0.923880, -0.382683, 0.500000),
   vec3(-0.707107, -0.707107, 0.625000),
   vec3(-1.000000, 0.000000, 0.500000),
   vec3(-0.816497, -0.577350, 0.625000),
   vec3(-0.707107, -0.707107, 0.625000),
   vec3(-0.382683, -0.923880, 0.750000),
   vec3(-0.923880, 0.382683, 0.500000),
   vec3(-0.985599, -0.169102, 0.625000),
   vec3(-1.000000, 0.000000, 0.625000),
   vec3(-0.707107, -0.707107, 0.750000),
   vec3(-0.707107, 0.707107, 0.625000),
   vec3(-0.923880, -0.382683, 0.750000),
   vec3(0.000000, 0.000000, 0.750000),
   vec3(-0.000000, -1.000000, 0.875000),
   vec3(-0.923880, 0.382683, 0.500000),
   vec3(-1.000000, 0.000000, 0.625000),
   vec3(-0.985599, 0.169102, 0.625000),
   vec3(-0.923880, -0.382683, 0.750000),
   vec3(-0.816497, 0.577350, 0.625000),
   vec3(-1.000000, 0.000000, 0.750000),
   vec3(-0.923880, 0.382683, 0.750000),
   vec3(-0.707107, -0.707107, 0.875000),
   vec3(-0.707107, 0.707107, 0.625000),
   vec3(-0.923880, 0.382683, 0.750000),
   vec3(-0.707107, 0.707107, 0.750000),
   vec3(-1.000000, 0.000000, 0.875000),
   vec3(-0.382683, 0.923880, 0.750000),
   vec3(-0.707107, 0.707107, 0.875000),
   vec3(-0.000000, 1.000000, 0.875000),
   vec3(0.000000, 0.000000, 1.000000)
);
// END GENERATED TOPOLOGY LUT ---

void main()
{
   highp vec2 srcCoordF = vTexCoord * global.SourceSize.xy;
   ivec2 coord = ivec2(floor(srcCoordF));
   ivec2 maxCoord = ivec2(global.SourceSize.xy) - ivec2(1);
   coord = clamp(coord, ivec2(0), maxCoord);

   // --- T-015/T-016: wide-kernel scalar statistics + four-class classification ---
   highp float L[25];
   highp vec3 C[25];
   int idx = 0;
   for (int dy = -2; dy <= 2; dy++)
      for (int dx = -2; dx <= 2; dx++)
      {
         ivec2 tapCoord = clamp(coord + ivec2(dx, dy), ivec2(0), maxCoord);
         vec3 rgb = texelFetch(Source, tapCoord, 0).rgb;
         C[idx] = rgb;
         L[idx] = luma(rgb);
         idx++;
      }

   highp float mean = 0.0;
   highp vec3 meanColor = vec3(0.0);
   for (int i = 0; i < 25; i++) { mean += L[i]; meanColor += C[i]; }
   mean /= 25.0;
   meanColor /= 25.0;

   highp float variance = 0.0;
   for (int i = 0; i < 25; i++) { highp float d = L[i] - mean; variance += d * d; }
   variance /= 25.0;

   const float SIGN[25] = float[25](
       1.0, -1.0,  1.0, -1.0,  1.0, -1.0,  1.0, -1.0,  1.0, -1.0,
       1.0, -1.0,  1.0, -1.0,  1.0, -1.0,  1.0, -1.0,  1.0, -1.0,
       1.0, -1.0,  1.0, -1.0,  1.0
   );
   highp float checkerRaw = 0.0;
   highp float spread = 0.0;
   for (int i = 0; i < 25; i++) { highp float d = L[i] - mean; checkerRaw += d * SIGN[i]; spread += abs(d); }
   checkerRaw /= 25.0;
   spread /= 25.0;
   highp float hasSignal = step(MIN_SPREAD, spread);
   highp float checkerboardAutocorr = hasSignal * abs(checkerRaw) / max(spread, MIN_SPREAD);

   const float BIN_WIDTH = 256.0 / 32.0;
   int mask = 0;
   for (int i = 0; i < 25; i++) { int bin = clamp(int(L[i] / BIN_WIDTH), 0, 31); mask |= (1 << bin); }
   float lumaBinPopcount = float(bitCount(mask));

   bool fg[25];
   for (int i = 0; i < 25; i++) fg[i] = L[i] >= mean;
   bool centerFg = fg[12];
   bool cur = fg[11];
   highp float rowLeft = 1.0 + float(cur); cur = cur && fg[10]; rowLeft += float(cur);
   cur = fg[13];
   highp float rowRight = 1.0 + float(cur); cur = cur && fg[14]; rowRight += float(cur);
   highp float rowRun = rowLeft + rowRight - 1.0;
   cur = fg[7];
   highp float colLeft = 1.0 + float(cur); cur = cur && fg[2]; colLeft += float(cur);
   cur = fg[17];
   highp float colRight = 1.0 + float(cur); cur = cur && fg[22]; colRight += float(cur);
   highp float colRun = colLeft + colRight - 1.0;
   highp float strokeWidth = centerFg ? min(rowRun, colRun) : 99.0;

   bool isDither = (checkerboardAutocorr >= CHECKERBOARD_HI) && (lumaBinPopcount <= POPCOUNT_DITHER_MAX);
   bool isStroke = (strokeWidth <= STROKE_WIDTH_MAX) && !isDither;
   bool isFlat = (variance <= VARIANCE_FLAT_MAX) && !isDither && !isStroke;

   vec3 centerColor = C[12]; // == texelFetch(Source, coord, 0).rgb
   vec3 outColor = centerColor;

   if (isDither)
   {
      // --- T-019: dither preservation ---
      highp float hardness = clamp(spread / SPREAD_HARD_REF, 0.0, 1.0);
      highp float blendAmount = (1.0 - hardness) * (1.0 - params.ARGUS_DITHER_STRENGTH);
      outColor = mix(centerColor, meanColor, blendAmount);
   }
   else if (isStroke)
   {
      // --- T-017: text/glyph protection — exact source color, no interpolation ---
      outColor = centerColor;
   }
   else if (false && !isFlat)
   {
      // T-046 experiment variant: T-018 edge reconstruction disabled
      // (condition short-circuited to false) — falls through to isFlat's
      // centerColor passthrough instead, to isolate how much of the IoU
      // gap against xBRZ/SABR/ScaleFX is attributable to edge
      // reconstruction specifically vs. text/stroke handling. Not a
      // proposed shipped change.
      // --- T-018: LUT-topology edge-directed reconstruction (classes a/c) ---
      int topoIndex = 0;
      const ivec2 OFFS[8] = ivec2[8](
         ivec2(0, -1), ivec2(1, -1), ivec2(1, 0), ivec2(1, 1),
         ivec2(0, 1), ivec2(-1, 1), ivec2(-1, 0), ivec2(-1, -1)
      );
      highp float threshLuma = params.ARGUS_EDGE_THRESHOLD * 255.0;
      highp float centerLuma = luma(centerColor);
      for (int bit = 0; bit < 8; bit++)
      {
         ivec2 nCoord = clamp(coord + OFFS[bit], ivec2(0), maxCoord);
         highp float nL = luma(texelFetch(Source, nCoord, 0).rgb);
         if (abs(nL - centerLuma) > threshLuma) topoIndex |= (1 << bit);
      }

      vec3 lutVal = TOPOLOGY_LUT[topoIndex];
      highp vec2 dir = lutVal.xy;
      highp float confidence = lutVal.z;

      if (confidence > 0.0)
      {
         highp vec2 frac = srcCoordF - (vec2(coord) + vec2(0.5));
         highp vec2 normal = vec2(-dir.y, dir.x);
         highp float dist = dot(frac, normal);
         ivec2 off = ivec2(clamp(round(normal), vec2(-1.0), vec2(1.0)));

         if (off.x != 0 || off.y != 0)
         {
            // confidence already gated whether to blend (above); it is
            // deliberately not also used to scale the blend amount here
            // — see tools/edge_reconstruct/report.md Finding 2.
            if (dist > 0.0)
            {
               ivec2 pCoord = clamp(coord + off, ivec2(0), maxCoord);
               highp float t = clamp(dist * 2.0, 0.0, 1.0);
               outColor = mix(centerColor, texelFetch(Source, pCoord, 0).rgb, t);
            }
            else
            {
               ivec2 nCoord2 = clamp(coord - off, ivec2(0), maxCoord);
               highp float t = clamp(-dist * 2.0, 0.0, 1.0);
               outColor = mix(centerColor, texelFetch(Source, nCoord2, 0).rgb, t);
            }
         }
      }
   }
   // isFlat: outColor stays centerColor — no reconstruction needed.

   FragColor = vec4(outColor, 1.0);
}
