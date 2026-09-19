#version 450

// T-018 — GLSL port of tools/edge_reconstruct/edge_reference.py's
// LUT-topology-driven edge reconstruction rule for classes (a)/(c). Debug/
// test-only shader, same status as classify_debug.slang / dither_debug.slang
// / text_debug.slang. See edge_reference.py's module docstring for the full
// rule and its independent-design provenance (docs/licensing.md).
//
// The topology LUT below is a GENERATED constant array (regenerate with
// tools/edge_reconstruct/regenerate_lut_glsl.py), not a sampled texture, even
// though T-014's baked topology_lut.png/.bin is the intended design for the
// real shipped pass (T-020) — this environment's Mesa/llvmpipe software
// rasterizer has a real, reproducible miscompilation when a *second* texture
// sampler is read with a dynamically-computed texelFetch index (isolated to
// a minimal repro in report.md Finding 1; a dynamically-indexed local array
// is unaffected, which is what makes this workaround possible at all). This
// only changes how *this pre-fusion debug shader* sources the LUT data in
// this specific test environment — T-020 should still use T-014's texture
// as designed, and re-verify that path against a real GPU driver rather than
// assuming this environment's limitation generalizes.
//
// Written as a single assignment to `outColor` selected by nested if/else
// (no early `return`), matching the workaround structure this shader was
// first debugged with — kept even though the actual miscompilation turned
// out to be the second-sampler issue above, since it's a harmless, equally
// readable style and there's no reason to reintroduce early returns now.

layout(set = 0, binding = 0, std140) uniform UBO
{
   mat4 MVP;
   vec4 SourceSize;
   vec4 OutputSize;
} global;

#pragma name EdgeReconstructDebug

#pragma parameter ARGUS_EDGE_THRESHOLD "Edge Detection Threshold" 0.10 0.0 1.0 0.01

layout(push_constant) uniform Push
{
   float ARGUS_EDGE_THRESHOLD;
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
const highp float VARIANCE_FLAT_MAX = 20.0;
const highp float STROKE_WIDTH_MAX = 2.0;
const highp float MIN_SPREAD = 0.5;

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

   // --- classification (same statistics/thresholds as classify_debug.slang) ---
   highp float L[25];
   int idx = 0;
   for (int dy = -2; dy <= 2; dy++)
      for (int dx = -2; dx <= 2; dx++)
      {
         ivec2 tapCoord = clamp(coord + ivec2(dx, dy), ivec2(0), maxCoord);
         L[idx] = luma(texelFetch(Source, tapCoord, 0).rgb);
         idx++;
      }

   highp float mean = 0.0;
   for (int i = 0; i < 25; i++) mean += L[i];
   mean /= 25.0;

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

   vec3 centerColor = texelFetch(Source, coord, 0).rgb;
   vec3 outColor = centerColor;

   if (!isDither && !isStroke && !isFlat)
   {
      // --- class (a)/(c): LUT-topology edge-directed reconstruction ---
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
            // `confidence` already gated whether to blend at all (the
            // `confidence > 0.0` check above); it is deliberately *not*
            // also used to scale the blend amount here. confidence is
            // popcount/8 (how many of 8 neighbors differ), which measures
            // how much of the topology is "edge-like," not how directionally
            // certain that edge's estimated tangent is — scaling the blend
            // by it was tried and measurably hurt sub-pixel edge-position
            // accuracy on the diagonal sweep (report.md Finding 2): a
            // genuine, confidently-classified edge (confidence < 1 is
            // common and expected, not a sign of low-quality data) still
            // deserves a full geometric blend along its estimated normal.
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

   FragColor = vec4(outColor, 1.0);
}
