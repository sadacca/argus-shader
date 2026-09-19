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
| [`docs/backlog.md`](docs/backlog.md) | 41 tickets across 5 phases, with acceptance criteria, dependencies, and the critical path |

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
GLES 3.1+ floor. **T-019** (dither preservation reconstruction rule) and **T-017** (text/glyph protection reconstruction
rule) are also built (`tools/dither_reconstruct/`, `tools/text_protect/`, see each `report.md`) —
verified the same way. Along the way, T-019 found that the existing synthetic corpus had no sample
isolating "soft" (SNES-style, close-color) ordered dithering, so a new `corpus/synthetic/dither_soft/`
category was added to actually test that acceptance criterion. T-017 found something more
significant: **T-010's text-negative corpus (fur/hair, architectural grids, weapon-outline
silhouettes) genuinely cannot be separated from real glyph strokes by T-015's four wide-kernel
statistics** — measured 80.8% false-positive rate, and a direct per-statistic check confirms no
threshold on the existing statistics would fix it. This isn't a new bug; T-004's original spike report
and T-010 both flagged this risk and deferred it to exactly this point. Tracked as new scope in
**T-041** rather than papered over — T-017's reconstruction rule itself is unaffected (nearest-
preserving reconstruction is a safe fallback even when misrouted; see `tools/text_protect/report.md`).

**T-018** (LUT-topology edge reconstruction, `tools/edge_reconstruct/`) is also built. Bringing it up
surfaced a real, reproducible Mesa/llvmpipe compiler bug — a dynamically-indexed `texelFetch` on a
second texture sampler corrupted unrelated shader state — isolated via bisection and worked around for
this pre-fusion debug shader (embedding the LUT as a generated GLSL constant array instead of sampling
its texture; the real shipped pass should still use the texture as T-014 designed, re-verified against
a real GPU driver). It also reports an honest non-result rather than a favorable cherry-pick: an
initial single-scale check showed this rule beating Omniscale on sub-pixel edge accuracy, but testing
across every scale this tier would realistically run at (2x-6x) shows it only wins 1 of 5 — that
acceptance box is left open with the full comparison table, not checked off.

Still genuinely blocked — real handheld bring-up (T-006), a real-game content corpus (T-007), and the
copyleft half of cataloging existing shaders' failure modes (T-011) — need a physical reference device
or a human call on licensing/content sourcing, not a tooling gap. Each is documented in
`docs/backlog-status.md` with what specifically would unblock it.

**Update, 2026-09-17 (continued once more): T-020 is built — mobile-lite is now a real, shippable
shader, not a skeleton.** `shaders/shaders_slang/argus/shaders/mobile-lite.slang` fuses T-016's
classifier with T-017/T-018/T-019's per-class reconstruction rules into the single output-resolution
pass FR3 requires. Fusion is verified exact against each already-correct contributing debug shader
(0-pixel difference, not a tolerance pass — see `tools/fusion/report.md`), the compile gate passes
clean on all five backends, and the render harness's 60 regression goldens all match. Along the way
this ticket found and fixed a real gap in the render harness's own goldens: they were pinned at
`scale0 = 1.0` (inherited from T-013's original passthrough skeleton), which made T-018's edge
reconstruction a mathematical no-op — a clean "PASS" that was silently checking nothing of this
ticket's logic. Fixed by testing at `scale0 = 4.0` (the middle of the realistic 2x-6x range), with
every regenerated golden visually spot-checked before committing. **This is the milestone the shader
is ready for a human to actually look at (UAT)** — see `tools/fusion/report.md`'s visual spot-check
table, or render any corpus sample through `argus-mobile-lite.slangp` directly.

Two threads carried in from earlier tickets remain open and untouched by T-020 — T-018's honest
Omniscale non-win (wins 1 of 5 tested scales) and T-041's classifier separability — plus two new ones
this ticket surfaced: `textureGather` adoption (a tracked perf optimization, not attempted) and the
`mediump`-vs-`highp` precision question T-015's own report flagged as deferred to T-020 (kept `highp`
throughout; downgrading without real hardware to catch an overflow regression would be an unverified
change). None of these block T-020 or UAT. **T-022** (Phase 1 exit validation — perceptual comparison,
bandwidth, frame time, false-positive-rate threshold) is the next item on the critical path and has
explicitly not been run yet; T-040's legacy-pack port of this fused logic also remains open.

**Update, 2026-09-17 (continued once more): a real comparison set against Omniscale, with a
documented glyph-preservation win.** `tools/comparison/` renders the full synthetic corpus through
argus-mobile-lite, Omniscale, and nearest-neighbour at matched scale (T-011). Headline result: on
glyph content, argus-mobile-lite is pixel-identical to nearest-neighbour (T-017's text protection
working as designed) while Omniscale visibly rounds glyph corners — the largest, most visually clear
gap in the set. ScaleFX (MIT, cleared) is vendored but not executable yet — it's a 6-pass filter
chain and this project's render harness is single-pass only. xBRZ/SABR/HQx were deliberately not
vendored or run at all — copyleft licenses with no permissive subset for execution, and T-011 already
flags that as a call for the project owner to make, not one to decide unilaterally. See
`tools/comparison/report.md` for the full breakdown.

**Update, 2026-09-18: T-042, a standardized ground-truth overlap metric, finished and committed** —
built the same session as T-011 but left uncommitted when that session was interrupted; picked back
up, re-verified (`run_eval.py` reproduces its own committed report byte-for-byte), and closed out.
`tools/eval_metric/` scores every executable baseline against IoU of a binarized shape mask from an
8x-supersampled ground truth, covering a curve and real letterforms rather than only straight lines.
Reported honestly rather than only citing T-011's favorable glyph result: **argus-mobile-lite loses
to Omniscale on this metric for 3 of 4 shapes**, winning only on the letterform T-011 already found
its glyph protection strongest on — a more mixed picture, and the same shape of honest non-win as
T-018's Omniscale comparison. See `tools/eval_metric/report.md`.

**Update, 2026-09-19: T-043, an analytical B/px lower bound — and a real concern for T-022.** T-021/
T-006 (measured bandwidth) remain blocked on physical handheld hardware this environment doesn't
have, but T-006's own acceptance criteria call for a *calculated* B/px to validate a future
measurement against — a hardware-independent number that didn't exist yet. Built it
(`tools/bandwidth_estimate/`): an ideal-cache amortized-bandwidth estimate of mobile-lite's actual
texture-read pattern, hand-verified against the shader source line-by-line. **Result: even under the
most generous plausible caching assumption, mobile-lite's bandwidth already exceeds §6's 8 B/px
ceiling at every scale in the realistic 2x-6x range** (15.1-40 B/px) — a direct, structural
consequence of FR3's single-output-resolution-pass design re-running the full 5×5 classification
kernel per output pixel rather than per native pixel (what Phase 2's T-023 exists to fix). Flagged
plainly rather than left for T-006's hardware to discover later: **T-022 should not be assumed to
pass its ≤8 B/px exit criterion as mobile-lite currently stands.** See
`tools/bandwidth_estimate/report.md`.

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
  text_protect/          T-017: text/glyph protection reconstruction rule + verify + report
                          (also surfaced T-041, a new open classifier-separability ticket)
  edge_reconstruct/      T-018: LUT-topology edge reconstruction + verify + report
                          (reference_shaders/: vendored MIT Omniscale, comparison-only)
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
