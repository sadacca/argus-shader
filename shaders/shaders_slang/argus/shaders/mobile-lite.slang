#version 450

// T-013 — root .slang skeleton for the mobile-lite tier. Independently
// authored structure per docs/licensing.md (T-001) — not derived from any
// reference shader's source.
//
// Declares the FR5 tunables (docs/requirements.md) and wires them through a
// push_constant block so they surface in RetroArch's shader menu. The
// fragment stage is presently a passthrough: two-level classification
// (T-014 LUT + T-015 scalar statistics), the FR2 region classifier (T-016),
// and per-class reconstruction (T-017-T-019) land in later tickets and get
// fused into this single pass per T-020, at which point the parameters
// below start actually driving reconstruction behavior.

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

void main()
{
   FragColor = texture(Source, vTexCoord);
}
