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
| [`docs/backlog.md`](docs/backlog.md) | 40 tickets across 5 phases, with acceptance criteria, dependencies, and the critical path |

## Status

Phase 0 (research & de-risking) is substantially complete. **T-004, the highest-risk item, passed**:
the two-level classifier separates intentional dithering from already-anti-aliased gradients
(0.906 vs. the 0.85 bar — see [`tools/classifier_spike/spike_report.md`](tools/classifier_spike/spike_report.md)),
so the architecture in `docs/requirements.md` §6a.3 stands and Phase 1 is not re-scoped.

Also done: licensing posture (T-001), the cross-backend compile gate (T-002), the GLES floor
decision (T-005), the synthetic test corpus (T-008/T-009/T-010), the perceptual A/B harness
(T-012), and the baked 3×3 topology LUT (T-014). See
[`docs/backlog-status.md`](docs/backlog-status.md) for the full rundown.

**Update, 2026-09-17:** this environment turned out to have a working software render backend after
all (Mesa llvmpipe/Lavapipe via headless EGL — no `/dev/dri` needed), which unblocked and then built
**T-003**, the golden-image regression harness (`tools/render_harness/`, 55 goldens seeded). Phase 1
has also started: root preset skeletons exist for both the primary `.slangp`/`.slang` pack (**T-013**)
and a newly-scoped parallel legacy `.glslp`/`.glsl` pack for pre-slang RetroArch installs (**T-040**),
both passthrough passes, both compiling clean and rendering byte-identical to their source through
the new harness. See `docs/backlog-status.md`'s 2026-09-17 update entries for what was actually built
and two real bugs the new tooling caught along the way (a GLSL ES precision-declaration ordering bug
in the legacy skeleton, and a silently-broken CI glob that meant shipped shaders were never actually
being compile-gated).

**Update, 2026-09-17 (continued):** the FR2 region classifier is built —
**T-015** (wide-kernel scalar statistics) and **T-016** (four-class classifier) are a GLSL port of
T-004's spike, verified against a CPU reference through the actual GLES render path
(`tools/classifier_gpu/`, see its `report.md`). Porting to GLSL caught two more real numerical bugs
(a 0/0-indeterminate checkerboard-autocorrelation ratio, and a unique-color-count proxy that needed
32 luma bins, not 8), plus a GLES-300-vs-310 toolchain mismatch below this project's own decided
GLES 3.1+ floor. **T-019** (dither preservation reconstruction rule) is also built
(`tools/dither_reconstruct/`, see its `report.md`) — verified the same way, and along the way found
that the existing synthetic corpus had no sample isolating "soft" (SNES-style, close-color) ordered
dithering, so a new `corpus/synthetic/dither_soft/` category was added to actually test that
acceptance criterion rather than assume an existing category covered it.

Still genuinely blocked — real handheld bring-up (T-006), a real-game content corpus (T-007), and the
copyleft half of cataloging existing shaders' failure modes (T-011) — need a physical reference device
or a human call on licensing/content sourcing, not a tooling gap. Each is documented in
`docs/backlog-status.md` with what specifically would unblock it. With T-015/T-016/T-019 done, the
remaining blockers on **T-020** (fuse into the single shipped mobile-lite pass, critical path) are
**T-017** (text/glyph protection) and **T-018** (edge reconstruction from LUT topology) — see
`docs/backlog-status.md` for recommended sequencing.

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
  compile_gate/          T-002: stub .slang pass + cross-backend compile check;
                          compile_check_legacy.py (T-040): legacy .glsl compile check
  classifier_spike/      T-004: offline classifier feasibility spike + report
  classifier_gpu/        T-015/T-016: GLSL classifier + CPU reference + verify + report
  dither_reconstruct/    T-019: dither-preservation reconstruction rule + verify + report
  patterns/               T-008/T-009/T-010: synthetic test corpus generators
  lut/                    T-014: 3x3 topology LUT generator + invariant tests
  ab_compare/             T-012: perceptual A/B comparison harness
  render_harness/         T-003: headless EGL/GLES render + golden-image diff/update
                          (goldens/ holds the committed reference PNGs)
shaders/
  shaders_slang/argus/     Primary .slangp/.slang pack (T-013)
  shaders_glsl/argus/      Parallel legacy .glslp/.glsl pack (T-040)
corpus/synthetic/        Generated test images (dither ramps, diagonal sweeps,
                          glyph sheets, checkerboard blocks, text pos/neg sets)
.github/workflows/
  compile-gate.yml        CI: T-002/T-040 compile gates + T-003 render harness
```
