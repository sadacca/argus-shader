# argus-shader

A next-generation upscaling shader for 8-bit and 16-bit console pixel art, targeting RetroArch / libretro (and librashader-based frontends) via standard `.slangp` presets — no core modifications required.

## Why

Retro upscaling algorithms (xBRZ, HQx, ScaleFX, SABR, Omniscale) have plateaued since the early 2010s. Known gaps remain around:

- Dithered and anti-aliased source art being destroyed as "noise" instead of preserved as intentional artist technique
- Diagonal/curve reconstruction artifacts
- Temporal shimmer on scrolling parallax backgrounds
- Weak performance on ARM/handheld GPUs

This project scopes and builds a shader (or shader pack) that closes those specific gaps rather than reinventing pixel-art scaling from scratch.

## Goals

- Sharp, clean upscaling that reads as an intentional HD remaster, not a blur or plastic-looking filter
- Correctly preserve deliberate SNES/Genesis-era dithering and color-blending tricks
- Reduce diagonal/curve artifacts beyond current ScaleFX/xBRZ baselines
- Basic temporal stabilization for scrolling parallax, without added input lag
- Ship as standard `.slangp` presets compatible with RetroArch and librashader
- Run acceptably on ARM handheld GPUs (Retroid/Anbernic/Steam Deck class), not just desktop
- Treat shader pass count as a first-class design constraint given mobile/tile-based GPUs are bandwidth-bound

## Non-goals

- Full vector-based "Depixelizing Pixel Art" reconstruction
- 3D/polygonal retro content (PS1/N64/Saturn) — 2D sprite/tile-based systems only for v1
- General photoreal ML super-resolution
- Replacing CRT/bezel shaders (Mega Bezel, CRT-Royale) — this composes with them, not competes

## Design overview

- **Tiered, pass-budgeted architecture**: mobile-lite (1 pass), mobile/mid (2 passes), and desktop/high (up to 4 passes) tiers, each a first-class shipped preset rather than a degraded fallback.
- **Dither/AA-aware edge classification** that also detects thin monochrome text/glyph strokes and routes them to a minimal-interpolation path, since font-scale text is a well-documented failure mode of xBRZ/HQx-style edge reconstruction.
- **Temporal stabilization via frame-history sampling** (slang spec history semantics) rather than a dedicated ping-pong pass, kept toggleable for latency-sensitive genres.
- **Dual-axis tuning profiles**: an independent system profile (NES/SMS, SNES/Genesis, GB/GBC/GBA) for dither conventions, and a genre profile (fast-action, scrolling-heavy, text/low-motion, static/turn-based) for temporal/sharpening/pass-budget behavior.

See [`docs/requirements.md`](docs/requirements.md) for the full requirements document, including the functional/non-functional requirements, mobile optimization strategy, integration path, validation plan, open questions, and suggested phasing.

## Status

Draft v0.1 — scoping document for future detailed R&D. No shader implementation yet.

## Project structure

```
docs/
  requirements.md   Full requirements document (functional/non-functional requirements, phasing, open questions)
```
