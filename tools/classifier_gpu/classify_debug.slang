#version 450

// T-015/T-016 — GLSL port of tools/classifier_gpu/reference.py, itself a
// GPU-friendly variant of tools/classifier_spike/classify.py (T-004).
// Debug/test-only shader, not part of any shipped preset: it exists so this
// math can be verified against the CPU reference through the T-003 render
// harness before it's fused into a shipped pass (T-020). Runs at scale 1.0
// (native resolution) and reads Source with texelFetch, matching the CPU
// reference's per-source-texel sliding window exactly — no interpolation.
//
// DEBUG_MODE selects the output encoding (verify_gpu.py decodes both):
//   0 = raw stats, encoded into RGBA for numeric tolerance comparison
//       against reference.py's compute_stats():
//         R = variance / 255.0 (clamped; luma variance can exceed 1.0)
//         G = checkerboard_autocorr (already ~[0,1])
//         B = luma_bin_popcount / 32.0
//         A = min(stroke_width, 99.0) / 99.0
//   1 = 4-class label (0=a flat/edge, 1=b dither, 2=c AA gradient,
//       3=d text/glyph stroke) written into R as label/3.0, for the same
//       eval_* accuracy metrics classify.py/reference.py compute on the
//       CPU side.
//
// A uniform (not per-pixel data-dependent) branch on DEBUG_MODE is used
// below to select the output encoding; this has no per-pixel divergence
// cost (every invocation in a draw takes the same branch), unlike the
// data-dependent per-pixel branching the FR2 hot path (T-016 proper, once
// fused into a shipped pass) needs to avoid — this file intentionally
// isn't that hot path, it's the reference implementation being verified
// before fusion.

layout(set = 0, binding = 0, std140) uniform UBO
{
   mat4 MVP;
   vec4 SourceSize;
   vec4 OutputSize;
} global;

#pragma name ClassifierDebug

#pragma parameter DEBUG_MODE "Debug Output Mode (0=stats,1=class)" 0.0 0.0 1.0 1.0

layout(push_constant) uniform Push
{
   float DEBUG_MODE;
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

// Classification thresholds — identical values to reference.py's THRESH,
// kept in lockstep manually (both files say so in a comment) until T-016
// promotes this into shared, generated tuning data instead of two
// hand-copied literals.
const highp float CHECKERBOARD_HI = 0.15;
const highp float POPCOUNT_DITHER_MAX = 2.0;
const highp float VARIANCE_FLAT_MAX = 20.0;
const highp float STROKE_WIDTH_MAX = 2.0;

highp float luma(vec3 c)
{
   return dot(c, vec3(0.299, 0.587, 0.114)) * 255.0;
}

void main()
{
   ivec2 coord = ivec2(vTexCoord * global.SourceSize.xy);
   ivec2 maxCoord = ivec2(global.SourceSize.xy) - ivec2(1);

   // Tap order matches reference.py's sliding_windows flatten order:
   // row-major over (dy, dx), both -2..2, so index = (dy+2)*5 + (dx+2).
   //
   // highp throughout this block is load-bearing, not decorative: the
   // variance accumulator sums up to 25 terms of (delta-luma)^2, each up
   // to 255^2 = 65025 — the sum can reach ~1.6M, which overflows real
   // fp16 mediump hardware (max ~65504) even though this environment's
   // software rasterizer won't necessarily reproduce that (mediump is
   // commonly implemented as fp32 on a software GL stack, so this can't
   // be fully verified here — see docs/backlog-status.md's T-015 note).
   highp float L[25];
   int idx = 0;
   for (int dy = -2; dy <= 2; dy++)
   {
      for (int dx = -2; dx <= 2; dx++)
      {
         // texelFetch is undefined outside [0,size) — clamp to edge
         // manually to match reference.py's np.pad(mode="edge").
         ivec2 tapCoord = clamp(coord + ivec2(dx, dy), ivec2(0), maxCoord);
         L[idx] = luma(texelFetch(Source, tapCoord, 0).rgb);
         idx++;
      }
   }

   highp float mean = 0.0;
   for (int i = 0; i < 25; i++) mean += L[i];
   mean /= 25.0;

   highp float variance = 0.0;
   for (int i = 0; i < 25; i++)
   {
      highp float d = L[i] - mean;
      variance += d * d;
   }
   variance /= 25.0;

   // (-1)^(dx+dy) checkerboard sign pattern, same tap order as above.
   const float SIGN[25] = float[25](
       1.0, -1.0,  1.0, -1.0,  1.0,
      -1.0,  1.0, -1.0,  1.0, -1.0,
       1.0, -1.0,  1.0, -1.0,  1.0,
      -1.0,  1.0, -1.0,  1.0, -1.0,
       1.0, -1.0,  1.0, -1.0,  1.0
   );
   highp float checkerRaw = 0.0;
   highp float spread = 0.0;
   for (int i = 0; i < 25; i++)
   {
      highp float d = L[i] - mean;
      checkerRaw += d * SIGN[i];
      spread += abs(d);
   }
   checkerRaw /= 25.0;
   spread /= 25.0;
   // checkerRaw/spread is a 0/0-like indeterminate form on a flat window:
   // measured on this project's own render path, a genuinely flat 5x5
   // window's ratio comes out noise-dominated (observed up to ~0.1, on
   // 77% of pixels in one test image) rather than exactly 0, because the
   // GPU's summation order doesn't hit the same exact float cancellation
   // a CPU reference sourced from identical uint8 taps does. MIN_SPREAD
   // (luma units, 0-255 scale) floors this branchlessly (`step`, not an
   // if) well above that noise floor and well below any real dithered-
   // pattern spread — see tools/classifier_gpu/reference.py's matching
   // guard for the full measurement.
   const highp float MIN_SPREAD = 0.5;
   highp float hasSignal = step(MIN_SPREAD, spread);
   highp float checkerboardAutocorr = hasSignal * abs(checkerRaw) / max(spread, MIN_SPREAD);

   // Unique-color-count proxy (see tools/classifier_gpu/reference.py's
   // N_LUMA_BINS comment for why 32, not the 8 first tried): OR each tap's
   // luma bin into a bitmask, bitCount it. One shift+OR per tap, one
   // bitCount total — this is the ALU-cheap replacement T-004's spike
   // flagged as needed for what was originally an O(k^2) distinct-count.
   const float BIN_WIDTH = 256.0 / 32.0;
   int mask = 0;
   for (int i = 0; i < 25; i++)
   {
      int bin = clamp(int(L[i] / BIN_WIDTH), 0, 31);
      mask |= (1 << bin);
   }
   float lumaBinPopcount = float(bitCount(mask));

   // Stroke-width: run-length of the foreground mask through the center
   // row/col, foreground defined as >= the window mean (matches
   // reference.py's center_run_length exactly, unrolled for the fixed 5x5
   // window instead of a loop — this is a compile-time-constant trip count
   // either way, so unrolling doesn't change divergence characteristics,
   // just makes the fixed indices explicit).
   bool fg[25];
   for (int i = 0; i < 25; i++) fg[i] = L[i] >= mean;
   bool centerFg = fg[12];

   bool cur = fg[11];
   highp float rowLeft = 1.0 + float(cur);
   cur = cur && fg[10];
   rowLeft += float(cur);
   cur = fg[13];
   highp float rowRight = 1.0 + float(cur);
   cur = cur && fg[14];
   rowRight += float(cur);
   highp float rowRun = rowLeft + rowRight - 1.0;

   cur = fg[7];
   highp float colLeft = 1.0 + float(cur);
   cur = cur && fg[2];
   colLeft += float(cur);
   cur = fg[17];
   highp float colRight = 1.0 + float(cur);
   cur = cur && fg[22];
   colRight += float(cur);
   highp float colRun = colLeft + colRight - 1.0;

   highp float strokeWidth = centerFg ? min(rowRun, colRun) : 99.0;

   if (params.DEBUG_MODE < 0.5)
   {
      FragColor = vec4(
         clamp(variance / 255.0, 0.0, 1.0),
         clamp(checkerboardAutocorr, 0.0, 1.0),
         lumaBinPopcount / 32.0,
         min(strokeWidth, 99.0) / 99.0
      );
   }
   else
   {
      bool isDither = (checkerboardAutocorr >= CHECKERBOARD_HI) && (lumaBinPopcount <= POPCOUNT_DITHER_MAX);
      bool isStroke = (strokeWidth <= STROKE_WIDTH_MAX) && !isDither;
      bool isFlat = (variance <= VARIANCE_FLAT_MAX) && !isDither && !isStroke;

      float label = 2.0; // default: gradient (c)
      label = isFlat ? 0.0 : label;
      label = isDither ? 1.0 : label;
      label = isStroke ? 3.0 : label;

      FragColor = vec4(label / 3.0, 0.0, 0.0, 1.0);
   }
}
