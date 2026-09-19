#version 450

// T-019 — GLSL port of tools/dither_reconstruct/reference.py's dither-
// preservation reconstruction rule. Debug/test-only shader (not part of any
// shipped preset, same status as tools/classifier_gpu/classify_debug.slang):
// exists to verify this math against the CPU reference through the T-003
// render harness before T-020 fuses it into the shipped mobile-lite pass.
// Runs at scale 1.0 (native resolution), texelFetch-only, matching the CPU
// reference's per-source-texel sliding window exactly.
//
// Classification statistics (variance/checkerboard/popcount/spread) are the
// exact same computation as classify_debug.slang — duplicated here rather
// than shared, matching this project's existing pattern of self-contained
// single-file .slang passes (no #include mechanism is in use anywhere in
// this repo yet). See reference.py's module docstring for the reconstruction
// rule's full rationale; this file only needs to match it numerically.

layout(set = 0, binding = 0, std140) uniform UBO
{
   mat4 MVP;
   vec4 SourceSize;
   vec4 OutputSize;
} global;

#pragma name DitherReconstructDebug

#pragma parameter ARGUS_DITHER_STRENGTH "Dither Preservation Strength" 1.0 0.0 1.0 0.05

layout(push_constant) uniform Push
{
   float ARGUS_DITHER_STRENGTH;
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

const highp float CHECKERBOARD_HI = 0.15;
const highp float POPCOUNT_DITHER_MAX = 2.0;
const highp float SPREAD_HARD_REF = 20.0;
const highp float MIN_SPREAD = 0.5;

highp float luma(vec3 c)
{
   return dot(c, vec3(0.299, 0.587, 0.114)) * 255.0;
}

void main()
{
   ivec2 coord = ivec2(vTexCoord * global.SourceSize.xy);
   ivec2 maxCoord = ivec2(global.SourceSize.xy) - ivec2(1);

   highp float L[25];
   highp vec3 C[25];
   int idx = 0;
   for (int dy = -2; dy <= 2; dy++)
   {
      for (int dx = -2; dx <= 2; dx++)
      {
         ivec2 tapCoord = clamp(coord + ivec2(dx, dy), ivec2(0), maxCoord);
         vec3 rgb = texelFetch(Source, tapCoord, 0).rgb;
         C[idx] = rgb;
         L[idx] = luma(rgb);
         idx++;
      }
   }

   highp float mean = 0.0;
   highp vec3 meanColor = vec3(0.0);
   for (int i = 0; i < 25; i++)
   {
      mean += L[i];
      meanColor += C[i];
   }
   mean /= 25.0;
   meanColor /= 25.0;

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
   highp float hasSignal = step(MIN_SPREAD, spread);
   highp float checkerboardAutocorr = hasSignal * abs(checkerRaw) / max(spread, MIN_SPREAD);

   const float BIN_WIDTH = 256.0 / 32.0;
   int mask = 0;
   for (int i = 0; i < 25; i++)
   {
      int bin = clamp(int(L[i] / BIN_WIDTH), 0, 31);
      mask |= (1 << bin);
   }
   float lumaBinPopcount = float(bitCount(mask));

   bool isDither = (checkerboardAutocorr >= CHECKERBOARD_HI) && (lumaBinPopcount <= POPCOUNT_DITHER_MAX);

   highp float hardness = clamp(spread / SPREAD_HARD_REF, 0.0, 1.0);
   highp float blendAmount = (1.0 - hardness) * (1.0 - params.ARGUS_DITHER_STRENGTH);

   vec3 hardColor = C[12]; // center tap == texelFetch(Source, coord, 0)
   vec3 dithered = mix(hardColor, meanColor, blendAmount);

   FragColor = vec4(isDither ? dithered : hardColor, 1.0);
}
