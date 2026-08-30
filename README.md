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

- **Tiered architecture budgeted by output-resolution passes**: mobile-lite (1 pass), mobile/mid (2 passes, 1 at output res), and desktop/high (up to 4 passes, ≤2 at output res). Each is a first-class shipped preset, not a degraded fallback. Budgeting *output-resolution* passes rather than total passes matters because a native-res intermediate costs ~0.2 bytes/output-pixel against ~8 for an output-res one.
- **Dither/AA-aware edge classification** using a two-level scheme — a 256-entry 3×3 topology LUT for edge geometry, plus cheap wide-kernel scalar statistics for region class. Also detects thin monochrome text/glyph strokes and routes them to a minimal-interpolation path, since font-scale text is a well-documented failure mode of xBRZ/HQx-style edge reconstruction.
- **Temporal stabilization via `OriginalHistory1`** — the previous frame's core input at *native* resolution, ~36× cheaper than reading back the previous frame's upscaled output, with no output-to-output feedback path to accumulate ghosting. Toggleable for latency-sensitive genres.
- **Dual-axis tuning profiles**: an independent system profile (NES/SMS, SNES/Genesis, GB/GBC/GBA) for dither conventions, and a genre profile (fast-action, scrolling-heavy, text/low-motion, static/turn-based) for temporal and sharpening behavior. RetroArch doesn't support references-to-references, so the two axes are merged at build time into a generated flat preset matrix.

Each tier carries a hard bandwidth ceiling in bytes per output pixel (8 / 10 / 32 B/px), measured rather than estimated — bandwidth, not ALU, is the binding constraint on the target hardware.

## Documentation

| Document | Contents |
|---|---|
| [`docs/requirements.md`](docs/requirements.md) | Full requirements — functional/non-functional requirements, mobile optimization strategy, integration path, validation plan, open questions, phasing with numeric exit criteria |
| [`docs/review-notes.md`](docs/review-notes.md) | v0.1 → v0.2 technical review: four blocking corrections, optimizations, and process fixes, with sources |
| [`docs/backlog.md`](docs/backlog.md) | 39 tickets across 5 phases, with acceptance criteria, dependencies, and the critical path |

## Status

Phase 0 (research & de-risking) is substantially complete. **T-004, the highest-risk item, passed**:
the two-level classifier separates intentional dithering from already-anti-aliased gradients
(0.906 vs. the 0.85 bar — see [`tools/classifier_spike/spike_report.md`](tools/classifier_spike/spike_report.md)),
so the architecture in `docs/requirements.md` §6a.3 stands and Phase 1 is not re-scoped.

Also done: licensing posture (T-001), the cross-backend compile gate (T-002), the GLES floor
decision (T-005), the synthetic test corpus (T-008/T-009/T-010), the perceptual A/B harness
(T-012), and the baked 3×3 topology LUT (T-014). See
[`docs/backlog-status.md`](docs/backlog-status.md) for the full rundown.

What's left in Phase 0 — the golden-image render harness (T-003), real handheld bring-up (T-006),
a real-game content corpus (T-007), and cataloging existing shaders' failure modes (T-011) — all
need something this build pass couldn't provide by itself: a GPU-capable environment, physical
reference hardware, or a human call on which homebrew titles to include. Each is documented in
`docs/backlog-status.md` with what specifically would unblock it. No shader implementation
(Phase 1, T-013 onward) has started yet.

## Project structure

```
docs/
  requirements.md      Full requirements document (v0.2)
  review-notes.md       Technical review behind the v0.2 revisions
  backlog.md            Phased ticket backlog with acceptance criteria
  backlog-status.md     What's done, what's blocked, and on what (this build session)
  licensing.md           T-001: license posture for reference shaders
  gles-floor.md          T-005: target-device GLES floor decision
tools/
  compile_gate/          T-002: stub .slang pass + cross-backend compile check
  classifier_spike/      T-004: offline classifier feasibility spike + report
  patterns/               T-008/T-009/T-010: synthetic test corpus generators
  lut/                    T-014: 3x3 topology LUT generator + invariant tests
  ab_compare/             T-012: perceptual A/B comparison harness
corpus/synthetic/        Generated test images (dither ramps, diagonal sweeps,
                          glyph sheets, checkerboard blocks, text pos/neg sets)
.github/workflows/
  compile-gate.yml        CI wiring for the T-002 compile gate
```
