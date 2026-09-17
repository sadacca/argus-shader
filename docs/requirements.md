# Requirements Document: Next-Gen 8/16-bit Upscaling Shader
**Status:** Draft v0.2 — scoping document for future detailed R&D
**Date:** 2026-08-30 (v0.1: 2026-08-29)

> **v0.2 revision note.** This revision folds in a technical review of v0.1 against the
> libretro slang shader spec and the stated ARM target hardware. Four items in v0.1 were
> not implementable as written and have been corrected: the preset composition model
> (§5 FR9), the LUT/kernel-size pairing (§5 FR8, §6a), the vertex-shader varying strategy
> (§6a), and the temporal history source (§5 FR4). The tier budget metric changed from
> total pass count to output-resolution pass count (§5 FR3, §6). See
> [`review-notes.md`](review-notes.md) for the reasoning behind each change.

---

## 1. Purpose & Background

Retro upscaling (xBRZ, HQx, ScaleFX, SABR, Omniscale) has plateaued algorithmically since the early 2010s. Real-time slang shaders in RetroArch now deliver most of that quality live via libretro cores, but known gaps remain around dithered/anti-aliased source art, diagonal-line artifacts, temporal stability, and ARM/handheld performance. This document scopes a new shader (or shader pack) intended to close those specific gaps — not to reinvent pixel-art scaling wholesale.

## 2. Goals

- Produce a sharper, cleaner presentation of 8-bit and 16-bit console art that reads as an *intentional* HD remaster, not a blurred or plastic-looking upscale.
- Correctly preserve deliberate dithering/color-blending techniques used by SNES/Genesis-era artists instead of destroying them as "noise."
- Reduce diagonal/curve artifacts beyond current ScaleFX/xBRZ baselines.
- Add basic temporal stabilization to reduce shimmer on scrolling parallax backgrounds.
- Ship as a standard `.slangp` preset pack compatible with RetroArch (and ideally librashader-based frontends) with no core modifications required.
- **Also ship a parallel legacy `.glslp`/`.glsl` preset pack** (added 2026-09-17) for RetroArch installs and frontends that predate or don't support the slang pipeline — see FR10.
- Run acceptably on ARM handheld GPUs (Retroid/Anbernic/Steam Deck class), not just desktop.
- Minimize **output-resolution** render passes as a first-class design constraint, not an afterthought — mobile/tile-based GPUs are bandwidth-bound, and each additional full-size render target costs a full-frame round trip.

## 3. Non-Goals

- Not attempting full "Depixelizing Pixel Art" vectorization (too fragile across arbitrary content).
- Not targeting 3D/polygonal retro content (PS1/N64/Saturn) — 2D sprite/tile-based systems only for v1.
- Not building a general photoreal ML super-resolution model; any learned component must be small enough for real-time inference on integrated/mobile GPUs, if used at all.
- Not replacing CRT/bezel simulation shaders (Mega Bezel, CRT-Royale) — this is a scaling shader intended to compose with them, not compete.

## 4. Current-State Survey (baseline to beat)

| Shader/Algorithm | Type | Strengths | Known weaknesses |
|---|---|---|---|
| **Nearest-neighbour integer scale** | Passthrough | Zero artifacts, zero cost, preserves authorial intent exactly; **the honest control** | Aliasing at non-integer scales, no smoothing at all |
| xBRZ (v1.9) | CPU pattern-matching | Strong edge/curve reconstruction, mature | Not native GPU shader; struggles with dithered art |
| ScaleFX | Multi-pass slang | Best-in-class contour smoothing | 4-5 passes, GPU-heavy, needs native core res input |
| SABR / Omniscale / HQ4x | Slang/GLSL | Fast, broad compatibility | Softer results, dated edge heuristics |
| Kopf–Lischinski (academic) | Vectorization | Resolution-independent, very clean on flat-color art | Fragile on AA/dithered/gradient art, complex pipeline |
| ML super-resolution (DLSS/FSR-style) | Neural, photoreal-focused | High quality on natural images | Not tuned for palette/dither preservation; real-time cost |

**Nearest-neighbour is a mandatory baseline in every comparison**, not a courtesy row. A meaningful
share of the target audience actively prefers unfiltered integer scaling; any perceptual study that
omits it cannot answer whether this shader improves on doing nothing.

## 5. Functional Requirements

1. **FR1 — Input handling:** Accept native core-resolution framebuffer input via the libretro/slang filter-chain `Source` texture; must work regardless of core-reported `base_width`/`base_height`, including mid-session geometry changes (e.g., SNES Mode 7, GBA layer changes).

2. **FR2 — Dither/AA-aware edge detection with text/glyph protection:** Classify local regions as (a) hard-edge/flat-color, (b) intentional dither/checkerboard pattern, (c) already-AA'd gradient, or (d) thin high-contrast monochrome strokes on a flat background (the signature of bitmap font glyphs), and apply a different reconstruction rule per class. Class (d) must route to a minimal-interpolation/nearest-preserving path rather than diagonal reconstruction, since font stroke widths (1-2 source pixels) don't carry enough neighborhood context for edge-reconstruction algorithms to classify correctly — this is a well-documented failure mode of xBRZ/HQx-style scalers on text, not a tuning issue. This must operate as a per-region rule within the single classifier, not a separate genre-selected shader, since a single frame (e.g., an RPG battle scene) typically mixes detailed art and text/UI overlay simultaneously.

3. **FR3 — Tiered architecture budgeted by output-resolution passes:** Structure as a `.slangp` filter chain following the [libretro slang shader spec](https://github.com/libretro/slang-shaders/blob/master/spec/SHADER_SPEC.md), with an explicit budget per tier.

   The budget metric is **passes that render at output resolution**, not total pass count. A
   native-resolution intermediate render target is nearly free: at 1080p output from a 256×224
   source, a native-res RT round trip costs ~0.2 bytes per output pixel, versus ~8 bytes for an
   output-res one — a ~36× difference. A 4-pass chain with three native-res passes is
   substantially cheaper than a 2-pass chain with two output-res passes, so counting total passes
   budgets the wrong resource.

   | Tier | Total passes | **Output-res passes** | Notes |
   |---|---|---|---|
   | Mobile-lite | 1 | 1 | Classification + reconstruction fused into one fragment shader, fixed unrolled neighborhood, no intermediate RTs |
   | Mobile/mid | 2 | 1 | Pass 1 native-res (see below); pass 2 upscale + sharpen + temporal |
   | Desktop/high | up to 4 | ≤ 2 | May add a dedicated smoothing/diffusion pass for maximum contour quality |

   **Mobile/mid pass-1 output is a classification + edge-parameter buffer, not a reconstructed
   image.** Pass 1 runs at native resolution and emits a compact 8-bit attachment (region class,
   dominant edge direction, blend weight); pass 2 consumes it and performs the actual expansion.
   Reconstructing at native resolution in pass 1 would discard the sub-pixel edge placement that
   the whole technique depends on, and contradicts the "expand late" principle in §6a.1.

   Every tier must be a first-class shipped preset, not a "reduced quality fallback" — mobile is a target platform, not a degraded mode.

4. **FR4 — Temporal stabilization via `OriginalHistory`, not `PassFeedback`:** Read prior-frame data directly inside the final pass rather than allocating a separate ping-pong pass. **The history source must be `OriginalHistory1` (previous frame's core input, at native resolution), not `PassFeedback` of the final pass (previous frame's output, at full output resolution).** Three reasons:

   - **Bandwidth.** At 1080p, a `PassFeedback` read of the final pass costs ~8.3 MB/frame (~500 MB/s at 60fps). `OriginalHistory1` at 256×224 costs ~229 KB/frame (~14 MB/s) — roughly 36× cheaper, on the axis the project has declared its primary budget.
   - **Ghosting.** `PassFeedback` blends output into its own input, so error accumulates across frames and small fast-moving sprites smear. Comparing *source* frames instead yields a per-pixel stability signal used to *modulate reconstruction strength*, with no output-to-output feedback path.
   - **Spec headroom.** `OriginalHistory#` supports arbitrary depth (VRAM-limited); `PassFeedback` is specified as a single frame. If 2-3 frames of history later prove useful for stability detection, only the history approach can supply them.

   The temporal term must remain toggleable for latency-sensitive genres (fighting games, shmups).

   *Spec constraint:* frames at N < 0 read as transparent black, so the first frames after load,
   reset, and save-state restore have no valid history and must degrade to the non-temporal path
   rather than blending against black.

5. **FR5 — Parameterization:** Expose tunables via `#pragma parameter` (edge threshold, dither-preservation strength, sharpen amount, temporal blend weight) so users can tune per-console/per-game.

6. **FR6 — Console-tuned presets:** Ship distinct presets for NES/SMS (low color depth, hard dithering), SNES/Genesis (16-bit dithering + transparency tricks), and handheld (GB/GBC/GBA) content, since their art conventions differ meaningfully. (See also FR9 for the fuller system-profile breakdown and its pairing with genre-based motion profiles.)

7. **FR7 — Aspect ratio / non-square pixel correctness:** Presets must respect each console's native pixel aspect ratio rather than assuming square pixels.

8. **FR8 — Bandwidth-conscious implementation:** Use fixed-offset texture reads, a **two-level classification scheme** (§6a.3) instead of divergent branching, mediump/8-bit intermediate formats on mobile tiers, and avoid unnecessary alpha channels in intermediate render targets. Offset computation strategy is specified in §6a.6 — note that the v0.1 guidance to precompute all offsets as vertex-shader varyings is **not viable** at the kernel sizes this design requires.

9. **FR9 — Dual-axis tuning profiles (system × genre), shipped as a generated preset matrix:** Provide two independent, low-cardinality parameter profiles rather than one entangled preset per game:

   - **Palette/dither profile** (per system): tunes the edge/dither classifier thresholds to match each system's known art conventions — e.g., NES (hard dithering, no hardware blending), SNES (larger palette + real alpha blending, less reliance on manual dither), Genesis/Mega Drive (heavy manual checkerboard dithering to fake colors/translucency — the case most easily destroyed by generic smoothing), GB/GBC (tiny palette, dither-heavy shading).
   - **Motion/genre profile**: tunes temporal blend strength, sharpening aggressiveness, **and pass-budget allocation** independent of system — e.g., fast-action (shmups/fighting games: minimal/no temporal blend to avoid ghosting on small fast-moving sprites, latency prioritized), scrolling-heavy (platformers: full temporal stabilization justified by parallax shimmer), text/low-motion (RPGs/strategy/adventure: reallocate the temporal-blend budget toward stronger text/glyph protection per FR2, since these genres are typically low-scroll and gain little from temporal stabilization but disproportionately benefit from font legibility), static/turn-based (temporal pass can be disabled entirely to save bandwidth).

   **These axes cannot compose at runtime and must be resolved at build time.** RetroArch's `#reference`
   mechanism permits exactly one level of indirection — *references to references are not supported* —
   so a chain of `base → system profile → genre override` is not expressible. There is no preset-level
   mechanism that merges two orthogonal parameter sets.

   The shipped artifact is therefore a **generated flat cross-product**: each (system × genre)
   combination is emitted as its own small `.slangp` containing a single `#reference` to the root
   preset plus the merged parameter values from both axes. With ~5 systems × 4 genres this is ~20
   generated files. They are produced by a build script from two small profile tables (one per axis)
   and are **never hand-maintained** — hand-editing 20 files to change one system threshold is how
   the axes silently become entangled again.

   The generated presets still map cleanly onto RetroArch's preset specificity hierarchy
   (global → core → content-directory → per-game, most specific wins), so a "Genesis + fast-action"
   combination ships as a directory or per-game preset override with no new engine mechanism required.

10. **FR10 — Dual-format distribution (`.slangp`/`.slang` and legacy `.glslp`/`.glsl`):** (added
    2026-09-17) Ship both the primary Vulkan-semantics slang pack and a parallel pack targeting
    RetroArch's older GLSL shader driver, for installs/frontends that don't support the slang
    pipeline. These are **not** the same artifact under two extensions — the legacy driver expects a
    structurally different file (`#if defined(VERTEX)`/`#elif defined(FRAGMENT)` single-file
    conditional compilation, `COMPAT_*` macros, implicit non-Vulkan uniform bindings) than what T-002's
    SPIR-V/spirv-cross cross-compile emits for the slang path, even though `#pragma parameter` syntax
    and the underlying reconstruction math are shared between the two. Each tier's algorithm should be
    ported to the legacy format as it lands, not written from scratch after the slang pack is
    finished. Confirm before FR4/temporal work lands on the legacy side whether the legacy GLSL
    driver's history/feedback model is equivalent to `OriginalHistory#` — the two drivers' semantics
    are not guaranteed to match.

## 6. Non-Functional Requirements

- **Performance budget:** Target 60fps at 1080p-4K output on mid-tier ARM handheld GPUs (e.g., Adreno 6xx/7xx class) using the **mobile-lite (1-pass) or mobile (2-pass) tier**, not the full desktop chain. The desktop tier's higher pass count is a separate, explicitly opt-in budget for hardware where bandwidth isn't the bottleneck.

- **Bandwidth is the primary budget metric, and is expressed as a number.** "Minimize passes" is not
  falsifiable; bytes per output pixel (B/px) is. Each tier carries a hard B/px ceiling for
  shader-attributable render-target traffic, measured rather than estimated:

  | Tier | B/px ceiling | Derivation |
  |---|---|---|
  | Mobile-lite | 8 B/px | One output-res write (4 B) + amortized native-res source taps |
  | Mobile/mid | 10 B/px | Above + native-res classification RT round trip (~0.2 B/px) + history read |
  | Desktop/high | 32 B/px | Above + up to 2 additional output-res RT round trips (8 B/px each) |

  For scale: at 4K60, 8 B/px ≈ 4.0 GB/s and 32 B/px ≈ 16 GB/s, against the ~12-17 GB/s of shared
  LPDDR4X typical of this handheld class — which is precisely why the desktop tier is not a mobile
  fallback. Pass count, render-target format size, and texture fetch count are tracked and reported
  per tier during development, not just frame time, since bandwidth-bound stalls hide behind an
  otherwise acceptable average frame time.

- **Backend portability:** Must compile/run correctly on GL (3.2+ unified slang driver), Vulkan, Direct3D 10/11/12, and Metal backends without backend-specific forks. **Validated continuously from Phase 0 as a build gate**, not as a Phase 2 porting exercise — a cross-compilation failure discovered after the algorithm is fixed is far more expensive than one caught on a stub pass.

- **Run-ahead and rewind compatibility:** Must not break RetroArch's run-ahead/rewind features. This interacts directly with FR4 and requires explicit testing rather than assumption: run-ahead re-simulates frames, and **rewind reverses frame order**, which will invert the sign of any motion signal derived from frame history. The temporal term must detect or tolerate both.

- **No core modification:** Must work purely as a shader preset — zero changes to libretro cores.

- **Latency:** Any temporal/history-based sampling must not introduce perceptible added input lag (target: <1 frame of visual lag contribution).

## 6a. Mobile Performance & Pass-Count Optimization Strategy

This is the core technical constraint for the mobile tier and should govern implementation decisions throughout, not just final optimization:

1. **Expand late.** Perform all multi-tap neighborhood analysis (edge detection, dither/AA classification) at the source's native low resolution, where total pixel count is small. Only the final pass should produce the large, upscaled output buffer. Never run expensive per-pixel analysis on an already-upscaled intermediate.

2. **Fuse instead of chain — but only for output-resolution passes.** Prefer one pass with a larger unrolled kernel over multiple passes with smaller kernels *when those passes would run at output resolution*. Mobile GPUs are comparatively ALU-rich and bandwidth-poor, so this trade favors fusion. It does **not** follow that native-resolution passes should be fused: splitting analysis across two native-res passes costs ~0.2 B/px and may well be cheaper than an oversized fused kernel that spills registers.

3. **Two-level classification: a 3×3 LUT plus wide-kernel scalar statistics.** A single LUT indexed by a
   wide neighborhood is not implementable, and v0.1 paired a 5×5/7×7 kernel with "index into a small,
   cache-friendly LUT" without reconciling the two. HQx's LUT works because a 3×3 neighborhood yields 8
   binary comparisons → 2⁸ = 256 entries. A 5×5 neighborhood yields 24 comparisons → 2²⁴ ≈ 16.7M
   entries, which is neither small nor cache-friendly. The two requirements are in direct conflict.

   Resolution — decompose by role:
   - **3×3 binary edge topology → 256-entry LUT.** This is the HQx-portable part and stays a genuine
     table lookup: cheap, divergence-free, and the exact thing LUTs are good at.
   - **5×5/7×7 wide kernel → cheap scalar statistics in ALU.** Local variance, checkerboard
     autocorrelation score, stroke-width estimate, unique-color count. No table, no branching — these
     are a handful of arithmetic ops on already-fetched taps.
   - The scalar statistics select *which reconstruction rule* the 3×3 LUT result is applied under
     (i.e. they pick the FR2 region class); the LUT supplies the edge geometry within that rule.

   This preserves both the wide-context classification FR2 needs and the divergence-free lookup FR8
   wants, without requiring a table that cannot exist.

4. **Use frame-history sampling for temporal terms.** Sample the previous frame's *core input* via `OriginalHistory1` inside the final pass instead of allocating a dedicated temporal blend pass. See FR4 for why the history semantic is preferred over pass feedback.

5. **Minimize render-target footprint.** Use 8-bit (not float) intermediate formats, drop alpha where not needed, and use mediump precision qualifiers on mobile-targeted GLSL/slang code paths.

6. **Offset strategy: fragment-shader constant offsets and `textureGather`, not varying-packed offsets.**
   v0.1 called for precomputing all sample offsets in the vertex shader and passing them as varyings.
   At the kernel sizes §6a.2 requires, this is counterproductive and in one case impossible:

   - **It does not fit.** Adreno 6xx-class hardware provides 16 vec4 varyings (64 components).
     A 5×5 kernel is 25 vec2 offsets ≈ 13 vec4 — 81% of the entire varying budget for offsets alone.
     A 7×7 kernel is 49 offsets ≈ 25 vec4, which **exceeds the hardware limit**; Freedreno reports GPU
     hangs above 16 vec4 on this family.
   - **It buys little on the target hardware.** The dependent-texture-read penalty this trick avoids
     is a PowerVR-era concern. On the Adreno 6xx/7xx class named in §6 it is largely absent, and the
     definition is narrower than v0.1 implies: a read is "dependent" when its coordinate derives from
     a *previously sampled value*, not merely because it was computed in the fragment shader. Adding
     a compile-time constant to an interpolated base coordinate is a non-dependent read.

   Correct guidance: pass the base coordinate and texel size as varyings (2 vec4 total), compute tap
   offsets in the fragment shader as constant adds, and prefer `textureGather` where available — it
   returns 4 texels per instruction, cutting a 25-tap 5×5 fetch to ~9 gathers. **`textureGather` is
   GLES 3.1+ / Vulkan**, so the mobile-lite tier must retain a scalar-fetch fallback path if it
   targets GLES 3.0 devices; confirm the floor of the target device matrix before depending on it.

7. **Profile on real reference hardware early.** Bandwidth bottlenecks on tile-based GPUs don't always show up in desktop GPU profiling — a low/mid-tier Android handheld (e.g., Retroid Pocket class) should be in the test loop from Phase 1, not bolted on at the end.

## 7. Integration Path (RetroArch / libretro)

- Distribute as a `.slangp` preset + associated `.slang` pass files, installable via the same folder structure as existing community shader packs (`shaders/shaders_slang/`).
- **Also distribute a parallel `.glslp` preset + associated `.glsl` pass files** (FR10), installable via the equivalent legacy folder structure (`shaders/shaders_glsl/`), for RetroArch installs and frontends without slang support.
- Validate against the [Slang Shader Spec](https://docs.libretro.com/development/shader/slang-shaders/) filter-chain model: each pass reads `Source` (prior pass or core input) and writes to a sized render target; final pass writes to backbuffer.
- Cross-check compatibility with **librashader**, the Rust reimplementation of the slang pipeline used by non-RetroArch frontends, to maximize reach beyond RetroArch itself.
- Test matrix should include: desktop (GL/Vulkan/D3D12), Steam Deck, at least one ARM handheld (Retroid/Anbernic), and macOS/Metal.
- Compose-test against popular bezel/CRT shaders (Mega Bezel, CRT-Royale) to confirm this shader can sit earlier in a combined filter chain without conflicting render-target assumptions.

## 8. Validation & Test Plan

**Automated regression (the default path).** Perceptual A/B comparison does not scale across
3 tiers × ~20 generated presets × N content items × 4 backends, and cannot gate a commit. The
primary harness is an offline, headless frame-dump comparator producing deterministic PNG output
per (content, preset, tier, backend) tuple, diffed against committed golden images. Perceptual
review becomes a spot-check on intentional changes rather than the mechanism that catches
regressions.

- Perceptual A/B comparisons against **nearest-neighbour integer scaling**, xBRZ, ScaleFX, SABR, and Omniscale using tools like imgsli, across a curated content set that deliberately includes: flat-color sprite art, dithered transparency effects, gradient skies, and fast-scrolling parallax.

- **Content corpus must be freely redistributable.** A public repository cannot ship captured frames
  from commercial ROMs. Build the corpus from homebrew and public-domain titles, plus **synthetic
  test patterns that isolate one failure mode each** (a dither ramp, a diagonal sweep at varying
  angles, a glyph sheet, a checkerboard-transparency block). Synthetic patterns are not a compromise
  here — they give cleaner signal than whole-game frames, where several effects are confounded in
  one image and a regression cannot be attributed.

- **Dedicated text/UI legibility test set:** dialogue boxes, menus, and HUD text from several RPGs with different bitmap font styles (thin sans-serif, outlined/drop-shadow fonts, larger blocky fonts), scored specifically for glyph shape fidelity and legibility, not just general image quality — this is a first-class pass/fail criterion, not folded into general perceptual scoring.

- **Text false-positive (negative) set is built before the glyph heuristic is tuned, not after.**
  Thin fur/hair line-art, fine architectural detail, pixel-thin weapon outlines. Tuning class (d)
  against a positive-only set optimizes a metric that rewards over-triggering — the heuristic will
  appear to succeed precisely by misclassifying art as text. Both sets gate the classifier together.

- **Temporal correctness cases** (gating FR4 and the run-ahead/rewind NFR): cold start with no
  history, save-state restore, rewind (reversed frame order), run-ahead frame re-simulation, and
  mid-session resolution change per FR1.

- Frame-time **and measured B/px** profiling per device tier (desktop GPU / Steam Deck / budget ARM handheld), checked against the §6 ceilings.

- Blind preference survey with retro-gaming community testers (forums.libretro.com, r/emulation) as a qualitative signal.

- Regression testing across dynamic-geometry cores (SNES Mode 7 titles, GBA affine transforms) to confirm FR1.

## 9. Open Questions

### Must be resolved in Phase 0 (they change how Phase 1 is written)

- **Licensing posture.** xBRZ, ScaleFX, and other reference shaders carry their own licenses (MIT/community). Confirm what may be referenced/derived from versus must be independently authored **before the first shader line is written.** Deciding this after Phase 1 risks a clean-room determination that invalidates existing work; it is a precondition, not an open question.
- **Two-level classifier feasibility (§6a.3).** Spike the 256-entry 3×3 LUT plus scalar-statistics decomposition and confirm it can express the four FR2 region classes with acceptable accuracy. This is the project's single riskiest technical bet — if the decomposition cannot separate dither from AA gradient, the architecture changes.
- **GLES floor of the target device matrix.** Whether `textureGather` (GLES 3.1+) can be depended on, or a 3.0 scalar-fetch fallback must be maintained in the mobile-lite tier (§6a.6).

### Genuinely open (answer during or after prototyping)

- Is a small learned (ML) component worth the added deployment complexity (model artifact, driver/runtime coupling) versus a purely hand-authored heuristic shader, given the performance/portability requirements?
- How much dither-preservation logic can be generalized vs. requires per-console tuning (Genesis and SNES use different dithering conventions)?
- Should temporal stabilization be on by default, or opt-in given latency-sensitive users (fighting games, shmups)?
- Does the text/glyph heuristic's false-positive rate against the negative set (§8) stay low enough to ship on by default, or does it need a user-facing toggle?
- What's the right balance between "faithful sharpened remaster" vs. "stylistic reinterpretation" — does this need a user-facing intensity slider from subtle to aggressive?

## 10. Suggested Phasing

Each phase has numeric exit criteria. A phase is not complete when its tickets are closed; it is
complete when its criteria are measured and met.

**Three tracks run in parallel throughout** — they share no code and serializing them wastes
calendar time:
- **Track A (shader core)** — the algorithm. Strictly sequential, Phase 1 → 3.
- **Track B (tooling/infra)** — test harness, golden-image CI, cross-compile gate, preset generator. Front-loaded in Phase 0, maintained after.
- **Track C (content/validation)** — corpus, positive and negative text sets, synthetic patterns. Front-loaded in Phase 0; **gates Phase 1's classifier tuning.**

---

1. **Phase 0 (research & de-risking).** Build the headless golden-image test harness and the
   side-by-side perceptual harness; catalog failure cases of existing shaders on target content.
   Stand up the cross-backend compile gate (GL/Vulkan/D3D/Metal) on a stub pass **now**, so
   portability is continuously enforced rather than discovered late. Build the redistributable
   content corpus including synthetic patterns and the text negative set. Resolve the three Phase-0
   open questions in §9. Acquire at least one low/mid-tier Android handheld as a standing reference
   device alongside desktop.
   *Exit criteria:* stub pass compiles clean on all 4 backends in CI; golden-image harness produces
   deterministic output across two consecutive runs on the same commit; corpus covers all four §8
   content categories plus the negative set; licensing posture documented and signed off.

2. **Phase 1 (mobile-first prototype).** Build the **1-pass mobile-lite tier first** — fused
   edge/dither classification + reconstruction, two-level classifier per §6a.3, mediump, no temporal
   term. Validate bandwidth/frame-time on the reference handheld before adding any feature. This
   becomes the performance floor everything else is measured against.
   *Exit criteria:* ≤ 8 B/px measured; 60fps at 1080p on the reference handheld; beats
   nearest-neighbour and SABR on the perceptual set; text legibility no worse than
   nearest-neighbour; false-positive rate on the negative set within the Phase-0 threshold.

3. **Phase 2 (expand).** Layer in the 2-pass mobile/mid tier — adds the native-res
   classification RT and the `OriginalHistory1` temporal term — plus the generated console-preset
   matrix and its build script. Backends are already green from Phase 0; this phase verifies
   *runtime* behavior per backend rather than porting.
   *Exit criteria:* ≤ 10 B/px measured; all temporal correctness cases in §8 pass, including rewind
   and run-ahead; preset matrix regenerates reproducibly from the profile tables; measured shimmer
   reduction on the parallax set with no ghosting regression on the fast-action set.

4. **Phase 3 (desktop tier & polish).** Add the higher-pass desktop tier for maximum quality where
   bandwidth isn't constrained; compose-test against Mega Bezel and CRT-Royale; community beta
   across all tiers.
   *Exit criteria:* ≤ 32 B/px measured; 60fps at 4K on desktop reference GPU; composes with at
   least one bezel and one CRT shader without render-target conflicts; blind survey shows
   preference over ScaleFX at equal or better frame time.

5. **Phase 4 (release).** Documentation (including per-tier guidance on which devices should use which preset), librashader compatibility confirmation, submission to the libretro slang-shaders community repo.
   *Exit criteria:* all tiers documented with device guidance; librashader parity confirmed on the golden-image set; upstream submission opened.
