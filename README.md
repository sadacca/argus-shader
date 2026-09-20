# argus-shader

A GPU upscaling shader for 8-bit and 16-bit console pixel art, targeting RetroArch / libretro (and
librashader-based frontends) via standard `.slangp` presets — no core modifications required.

## Goal

Treat 8/16-bit sprite and tile art as a low-resolution rasterization of art that implies shapes,
curves, and letterforms beyond what the pixel grid can express — the same working assumption xBRZ,
HQx, Omniscale, ScaleFX, and SABR already make — and reconstruct that continuous art as faithfully as
possible, rather than leaving it blocky. The differentiator against the existing field is **text and
glyph fidelity**: a well-documented weak point of these scalers (Omniscale visibly rounds glyph
corners — see `tools/gold_eval/report.md`), and the content type players spend the most continuous
time looking directly at.

## Explicit pivot (2026-09-20)

An earlier version of this project optimized for the opposite goal — preserving the source's blocky
pixel grid and hand-placed dithering as an intentional artifact, with text specially routed to a
"keep it blocky" path. This project's own gold-standard eval and real RetroArch testing both showed
that was a mistake: it made the shader the worst candidate of six on genuinely smooth/curved content
(tying or losing to doing nothing at all) while only winning on already-blocky content nobody asked
to have preserved. **Preserving the blocky aesthetic is not a goal of this project.**
`docs/requirements.md` has been rewritten around the corrected goal above.

## Non-goals

- Preserving the source's blocky pixel grid or deliberate dithering as a protected texture — the
  opposite of the goal above.
- Full spline/vector-file output (Depixelizing Pixel Art-style vectorization) — this stays a
  real-time raster shader; "vector-faithful" describes the reconstruction goal, not the output format.
- 3D/polygonal retro content (PS1/N64/Saturn) — 2D sprite/tile-based systems only.
- General photoreal ML super-resolution.
- Replacing CRT/bezel shaders (Mega Bezel, CRT-Royale) — composes with them, doesn't compete.

## Documentation

| Document | Contents |
|---|---|
| [`docs/requirements.md`](docs/requirements.md) | Full spec — goals, non-goals, functional/non-functional requirements, validation plan |
| [`docs/backlog.md`](docs/backlog.md) | Reusable infra, retired work, and what's next |
| [`docs/backlog-status.md`](docs/backlog-status.md) | Current status and why the pivot happened |
| [`docs/licensing.md`](docs/licensing.md) | License posture for reference shaders (xBRZ, ScaleFX, SABR, Omniscale, HQx) |
| [`docs/gles-floor.md`](docs/gles-floor.md) | Target-device GLES floor decision |
| [`docs/retroarch-testing.md`](docs/retroarch-testing.md) | How to load and A/B test presets in a real RetroArch install |
| [`docs/review-notes.md`](docs/review-notes.md) | Engineering corrections from the v0.1→v0.2 review (items still valid are marked; superseded ones are noted) |

## Status

Direction just changed (see pivot note above); the reconstruction algorithm itself is being
redesigned from that corrected goal. What survives the pivot and is ready to reuse:

- **Evaluation harness** — headless golden-image render harness (`tools/render_harness/`),
  ground-truth IoU scoring (`tools/eval_metric/`), the gold-standard V-corner/O-ring vector-vs-8bit
  regime eval that's now the primary quality gate (`tools/gold_eval/`), perceptual A/B comparison
  (`tools/ab_compare/`), and a working multi-pass renderer that runs real reference shaders —
  nearest-neighbour, Omniscale, SABR, ScaleFX, xBRZ — for direct comparison (`tools/comparison/`).
- **Build/CI infra** — cross-backend compile gate for both the slang and legacy GLSL packs
  (`tools/compile_gate/`), synthetic test corpus generators (`tools/patterns/`).
- **Decided groundwork** — licensing posture, GLES floor, preset pack structure.

What's retired: the dither-vs-AA-gradient classifier, the text-to-nearest-neighbour protection path,
and the shipped `mobile-lite.slang` prototype built on both. Kept in git history, not the current
direction. Full breakdown: `docs/backlog-status.md`.

## Project structure

```
docs/                     Requirements, backlog, and decision records (see table above)
tools/
  render_harness/          Headless EGL/GLES render + golden-image diff/update
  eval_metric/              Ground-truth IoU scoring against a supersampled reference
  gold_eval/                V-corner/O-ring vector-regime vs. 8bit-regime eval — the primary quality gate
  ab_compare/               Perceptual A/B comparison harness
  comparison/               Runs nearest-neighbour/Omniscale/SABR/ScaleFX/xBRZ for direct comparison
  compile_gate/             Cross-backend (.slang + legacy .glsl) compile check
  patterns/                 Synthetic test corpus generators
  <others>                  Earlier prototype work — see docs/backlog-status.md for what's retired
shaders/
  shaders_slang/argus/      Primary .slangp/.slang pack
  shaders_glsl/argus/       Parallel legacy .glslp/.glsl pack
corpus/synthetic/          Generated test images
.github/workflows/
  compile-gate.yml          CI: compile gates + render harness
```
