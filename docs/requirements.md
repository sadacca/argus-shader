# Requirements Document: Next-Gen 8/16-bit Upscaling Shader
**Status:** Draft v0.1 — scoping document for future detailed R&D
**Date:** 2026-08-29

---

## 1. Purpose & Background

Retro upscaling (xBRZ, HQx, ScaleFX, SABR, Omniscale) has plateaued algorithmically since the early 2010s. Real-time slang shaders in RetroArch now deliver most of that quality live via libretro cores, but known gaps remain around dithered/anti-aliased source art, diagonal-line artifacts, temporal stability, and ARM/handheld performance. This document scopes a new shader (or shader pack) intended to close those specific gaps — not to reinvent pixel-art scaling wholesale.

## 2. Goals

- Produce a sharper, cleaner presentation of 8-bit and 16-bit console art that reads as an *intentional* HD remaster, not a blurred or plastic-looking upscale.
- Correctly preserve deliberate dithering/color-blending techniques used by SNES/Genesis-era artists instead of destroying them as "noise."
- Reduce diagonal/curve artifacts beyond current ScaleFX/xBRZ baselines.
- Add basic temporal stabilization to reduce shimmer on scrolling parallax backgrounds.
- Ship as a standard `.slangp` preset pack compatible with RetroArch (and ideally librashader-based frontends) with no core modifications required.
- Run acceptably on ARM handheld GPUs (Retroid/Anbernic/Steam Deck class), not just desktop.
- Minimize shader pass count as a first-class design constraint, not an afterthought — mobile/tile-based GPUs are bandwidth-bound, and each additional pass costs a full-frame render-target round trip.

## 3. Non-Goals

- Not attempting full "Depixelizing Pixel Art" vectorization (too fragile across arbitrary content).
- Not targeting 3D/polygonal retro content (PS1/N64/Saturn) — 2D sprite/tile-based systems only for v1.
- Not building a general photoreal ML super-resolution model; any learned component must be small enough for real-time inference on integrated/mobile GPUs, if used at all.
- Not replacing CRT/bezel simulation shaders (Mega Bezel, CRT-Royale) — this is a scaling shader intended to compose with them, not compete.

## 4. Current-State Survey (baseline to beat)

| Shader/Algorithm | Type | Strengths | Known weaknesses |
|---|---|---|---|
| xBRZ (v1.9) | CPU pattern-matching | Strong edge/curve reconstruction, mature | Not native GPU shader; struggles with dithered art |
| ScaleFX | Multi-pass slang | Best-in-class contour smoothing | 4-5 passes, GPU-heavy, needs native core res input |
| SABR / Omniscale / HQ4x | Slang/GLSL | Fast, broad compatibility | Softer results, dated edge heuristics |
| Kopf–Lischinski (academic) | Vectorization | Resolution-independent, very clean on flat-color art | Fragile on AA/dithered/gradient art, complex pipeline |
| ML super-resolution (DLSS/FSR-style) | Neural, photoreal-focused | High quality on natural images | Not tuned for palette/dither preservation; real-time cost |

## 5. Functional Requirements

1. **FR1 — Input handling:** Accept native core-resolution framebuffer input via the libretro/slang filter-chain `Source` texture; must work regardless of core-reported `base_width`/`base_height`, including mid-session geometry changes (e.g., SNES Mode 7, GBA layer changes).
2. **FR2 — Dither/AA-aware edge detection with text/glyph protection:** Classify local regions as (a) hard-edge/flat-color, (b) intentional dither/checkerboard pattern, (c) already-AA'd gradient, or (d) thin high-contrast monochrome strokes on a flat background (the signature of bitmap font glyphs), and apply a different reconstruction rule per class. Class (d) must route to a minimal-interpolation/nearest-preserving path rather than diagonal reconstruction, since font stroke widths (1-2 source pixels) don't carry enough neighborhood context for edge-reconstruction algorithms to classify correctly — this is a well-documented failure mode of xBRZ/HQx-style scalers on text, not a tuning issue. This must operate as a per-region rule within the single classifier, not a separate genre-selected shader, since a single frame (e.g., an RPG battle scene) typically mixes detailed art and text/UI overlay simultaneously.
3. **FR3 — Tiered, pass-budgeted architecture:** Structure as a `.slangp` filter chain following the [libretro slang shader spec](https://github.com/libretro/slang-shaders/blob/master/spec/SHADER_SPEC.md), but with an explicit pass-count budget per tier rather than one fixed pipeline:
   - **Mobile-lite tier: 1 pass.** Edge/dither classification and reconstruction fused into a single fragment shader using a fixed unrolled neighborhood (no intermediate render targets).
   - **Mobile/mid tier: 2 passes max.** Classification+reconstruction in pass 1 at native resolution; final upscale+sharpen+temporal blend in pass 2.
   - **Desktop/high tier: up to 4 passes.** May add a dedicated smoothing/diffusion pass for maximum contour quality where bandwidth is not the constraint.
   Every tier must be a first-class shipped preset, not a "reduced quality fallback" — mobile is a target platform, not a degraded mode.
4. **FR4 — Temporal stabilization via history semantics, not a dedicated pass:** Use the slang spec's frame-history sampling (`OriginalHistory`/`PassFeedback`-style semantics) to read the previous *frame's* output directly inside the final pass, rather than allocating a separate ping-pong pass. This delivers shimmer reduction without adding a pass or a second full-frame read/write cycle. Must remain toggleable for latency-sensitive genres (fighting games, shmups).
5. **FR5 — Parameterization:** Expose tunables via `#pragma parameter` (edge threshold, dither-preservation strength, sharpen amount, temporal blend weight) so users can tune per-console/per-game.
6. **FR6 — Console-tuned presets:** Ship distinct presets for NES/SMS (low color depth, hard dithering), SNES/Genesis (16-bit dithering + transparency tricks), and handheld (GB/GBC/GBA) content, since their art conventions differ meaningfully. (See also FR9 for the fuller system-profile breakdown and its pairing with genre-based motion profiles.)
7. **FR7 — Aspect ratio / non-square pixel correctness:** Presets must respect each console's native pixel aspect ratio rather than assuming square pixels.
8. **FR8 — Bandwidth-conscious implementation:** Use non-dependent texture reads with fixed offsets (precomputed in the vertex shader where possible), LUT-based neighborhood classification instead of divergent branching, mediump/8-bit intermediate formats on mobile tiers, and avoid unnecessary alpha channels in intermediate render targets.
9. **FR9 — Dual-axis tuning profiles (system × genre):** Provide two independent, low-cardinality parameter profiles rather than one entangled preset per game:
   - **Palette/dither profile** (per system): tunes the edge/dither classifier thresholds to match each system's known art conventions — e.g., NES (hard dithering, no hardware blending), SNES (larger palette + real alpha blending, less reliance on manual dither), Genesis/Mega Drive (heavy manual checkerboard dithering to fake colors/translucency — the case most easily destroyed by generic smoothing), GB/GBC (tiny palette, dither-heavy shading).
   - **Motion/genre profile**: tunes temporal blend strength, sharpening aggressiveness, **and pass-budget allocation** independent of system — e.g., fast-action (shmups/fighting games: minimal/no temporal blend to avoid ghosting on small fast-moving sprites, latency prioritized), scrolling-heavy (platformers: full temporal stabilization justified by parallax shimmer), text/low-motion (RPGs/strategy/adventure: reallocate the temporal-blend pass slot toward stronger text/glyph protection per FR2, since these genres are typically low-scroll and gain little from temporal stabilization but disproportionately benefit from font legibility), static/turn-based (temporal pass can be disabled entirely to save bandwidth).
   These two axes combine multiplicatively via preset parameter sets rather than requiring separate shader code per combination, and map directly onto RetroArch's existing shader-preset specificity hierarchy (global → core → content-directory → per-game, most specific wins) — so a "Genesis + fast-action" combination ships as a directory or per-game preset override with no new engine mechanism required.

## 6. Non-Functional Requirements

- **Performance budget:** Target 60fps at 1080p-4K output on mid-tier ARM handheld GPUs (e.g., Adreno 6xx/7xx class) using the **mobile-lite (1-pass) or mobile (2-pass) tier**, not the full desktop chain. The desktop tier's higher pass count is a separate, explicitly opt-in budget for hardware where bandwidth isn't the bottleneck.
- **Bandwidth is the primary budget metric, not ALU cycles.** Pass count, render-target format size, and texture fetch count should be tracked and reported per tier during development — not just frame time — since bandwidth-bound stalls can hide behind an otherwise acceptable average frame time.
- **Backend portability:** Must compile/run correctly on GL (3.2+ unified slang driver), Vulkan, Direct3D 10/11/12, and Metal backends without backend-specific forks.
- **Run-ahead compatibility:** Must not break RetroArch's run-ahead/rewind features (i.e., avoid assumptions that break on frame re-simulation).
- **No core modification:** Must work purely as a shader preset — zero changes to libretro cores.
- **Latency:** Any temporal/history-based sampling must not introduce perceptible added input lag (target: <1 frame of visual lag contribution).

## 6a. Mobile Performance & Pass-Count Optimization Strategy

This is the core technical constraint for the mobile tier and should govern implementation decisions throughout, not just final optimization:

1. **Expand late.** Perform all multi-tap neighborhood analysis (edge detection, dither/AA classification) at the source's native low resolution, where total pixel count is small. Only the final pass should produce the large, upscaled output buffer. Never run expensive per-pixel analysis on an already-upscaled intermediate.
2. **Fuse instead of chain.** Prefer one pass with a larger unrolled kernel (e.g., 5x5/7x7, fixed offsets) over multiple passes with smaller kernels. Mobile GPUs are comparatively ALU-rich and bandwidth-poor, so this trade generally favors fusion.
3. **LUT-based classification over branching.** Encode local neighborhood comparisons as a bit pattern and index into a small, cache-friendly LUT texture rather than using divergent conditional logic — mirrors how HQx's original CPU lookup-table approach can be ported to a GPU-friendly form.
4. **Use built-in frame-history sampling for temporal terms.** Sample the previous frame's output directly via the slang spec's history semantics inside the final pass instead of allocating a dedicated temporal blend pass.
5. **Minimize render-target footprint.** Use 8-bit (not float) intermediate formats, drop alpha where not needed, and use mediump precision qualifiers on mobile-targeted GLSL/slang code paths.
6. **Non-dependent texture reads.** Precompute sample offsets in the vertex shader and pass them as varyings where the hardware supports it, avoiding runtime-computed texture coordinates in the fragment shader.
7. **Profile on real reference hardware early.** Bandwidth bottlenecks on tile-based GPUs don't always show up in desktop GPU profiling — a low/mid-tier Android handheld (e.g., Retroid Pocket class) should be in the test loop from Phase 1, not bolted on at the end.

## 7. Integration Path (RetroArch / libretro)

- Distribute as a `.slangp` preset + associated `.slang` pass files, installable via the same folder structure as existing community shader packs (`shaders/shaders_slang/`).
- Validate against the [Slang Shader Spec](https://docs.libretro.com/development/shader/slang-shaders/) filter-chain model: each pass reads `Source` (prior pass or core input) and writes to a sized render target; final pass writes to backbuffer.
- Cross-check compatibility with **librashader**, the Rust reimplementation of the slang pipeline used by non-RetroArch frontends, to maximize reach beyond RetroArch itself.
- Test matrix should include: desktop (GL/Vulkan/D3D12), Steam Deck, at least one ARM handheld (Retroid/Anbernic), and macOS/Metal.
- Compose-test against popular bezel/CRT shaders (Mega Bezel, CRT-Royale) to confirm this shader can sit earlier in a combined filter chain without conflicting render-target assumptions.

## 8. Validation & Test Plan

- Perceptual A/B comparisons against xBRZ, ScaleFX, SABR, Omniscale using tools like imgsli, across a curated content set that deliberately includes: flat-color sprite art, dithered transparency effects, gradient skies, and fast-scrolling parallax.
- **Dedicated text/UI legibility test set:** dialogue boxes, menus, and HUD text from several RPGs with different bitmap font styles (thin sans-serif, outlined/drop-shadow fonts, larger blocky fonts), scored specifically for glyph shape fidelity and legibility, not just general image quality — this should be a first-class pass/fail criterion, not folded into general perceptual scoring.
- Frame-time profiling per device tier (desktop GPU / Steam Deck / budget ARM handheld).
- Blind preference survey with retro-gaming community testers (forums.libretro.com, r/emulation) as a qualitative signal.
- Regression testing across dynamic-geometry cores (SNES Mode 7 titles, GBA affine transforms) to confirm FR1.

## 9. Open Questions for Further Research

- Is a small learned (ML) component worth the added deployment complexity (model artifact, driver/runtime coupling) versus a purely hand-authored heuristic shader, given the performance/portability requirements?
- How much dither-preservation logic can be generalized vs. requires per-console tuning (Genesis and SNES use different dithering conventions)?
- Should temporal stabilization be on by default, or opt-in given latency-sensitive users (fighting games, shmups)?
- **Text/glyph detection false-positive risk:** a heuristic tuned to catch thin, high-contrast monochrome strokes (font glyphs) may misfire on legitimate art content with similar characteristics — e.g., thin fur/hair line-art, fine architectural detail, or pixel-thin weapon outlines — leaving them under-reconstructed. This needs explicit false-positive testing against non-text high-detail sprite content, not just validation that text improves.
- What's the right balance between "faithful sharpened remaster" vs. "stylistic reinterpretation" — does this need a user-facing intensity slider from subtle to aggressive?
- Licensing: xBRZ, ScaleFX, and other reference shaders have their own licenses (MIT/community); confirm what can be referenced/derived from vs. must be independently authored.

## 10. Suggested Phasing

1. **Phase 0 (research):** Build side-by-side test harness (imgsli or custom), catalog failure cases of existing shaders on target content. Acquire at least one low/mid-tier Android handheld as a standing reference device alongside desktop.
2. **Phase 1 (mobile-first prototype):** Build the **1-pass mobile-lite tier first** — fused edge/dither classification + reconstruction, LUT-based, mediump, no temporal term. Validate bandwidth/frame-time on the reference handheld before adding any feature. This becomes the performance floor everything else is measured against.
3. **Phase 2 (expand):** Layer in the 2-pass mobile/mid tier (adds history-based temporal term via frame-history sampling) and console-tuned presets; port across GL/Vulkan/D3D/Metal backends.
4. **Phase 3 (desktop tier & polish):** Add the higher-pass desktop tier for maximum quality where bandwidth isn't constrained; community beta across both tiers.
5. **Phase 4 (release):** Documentation (including per-tier guidance on which devices should use which preset), submission to libretro slang-shaders community repo.
