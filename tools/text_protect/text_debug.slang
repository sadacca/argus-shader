#version 450

// T-017 — GLSL port of tools/text_protect/text_reference.py's class-(d)
// text/glyph protection reconstruction rule. Debug/test-only shader, same
// status as classify_debug.slang / dither_debug.slang: verifies this math
// against a CPU reference through T-003's render harness before T-020 fuses
// it into the shipped pass. Runs at scale 1.0, texelFetch-only.
//
// DEBUG_MODE 0 = "protected": class (d) pixels output their exact source
//   color; everything else falls back to the local 5x5-mean placeholder
//   (not this ticket's job to build classes a/c's real reconstruction).
// DEBUG_MODE 1 = "unprotected": every pixel goes through the same
//   local-mean placeholder regardless of class — the comparison baseline
//   representing "no class-(d) special case at all," i.e. what this ticket
//   exists to prevent. A uniform branch, no per-pixel divergence.

layout(set = 0, binding = 0, std140) uniform UBO
{
   mat4 MVP;
   vec4 SourceSize;
   vec4 OutputSize;
} global;

#pragma name TextProtectDebug

#pragma parameter DEBUG_MODE "Debug Output Mode (0=protected,1=unprotected)" 0.0 0.0 1.0 1.0

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

const highp float CHECKERBOARD_HI = 0.15;
const highp float POPCOUNT_DITHER_MAX = 2.0;
const highp float STROKE_WIDTH_MAX = 2.0;
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

   bool isDither = (checkerboardAutocorr >= CHECKERBOARD_HI) && (lumaBinPopcount <= POPCOUNT_DITHER_MAX);
   bool isStroke = (strokeWidth <= STROKE_WIDTH_MAX) && !isDither;

   vec3 hardColor = C[12];
   vec3 protectedOut = isStroke ? hardColor : meanColor;

   FragColor = vec4(params.DEBUG_MODE < 0.5 ? protectedOut : meanColor, 1.0);
}
