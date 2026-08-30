#version 450

// T-002 stub pass: the minimal valid .slang structure per the libretro slang
// shader spec (docs/backlog.md T-002). This is a passthrough — its only job
// is to exercise the full parse -> SPIR-V -> per-backend cross-compile
// pipeline so portability is enforced from commit one (docs/review-notes.md
// P1), before any real algorithm exists.

layout(set = 0, binding = 0, std140) uniform UBO
{
   mat4 MVP;
   vec4 SourceSize;
   vec4 OutputSize;
} global;

#pragma name StubPass

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
