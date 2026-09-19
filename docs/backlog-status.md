# Backlog status — build session 2026-08-30

Tracks what this build session completed against `docs/backlog.md`, and — since the session ran in
a container with no GPU (`/dev/dri` absent) and no physical device — records exactly which Phase 0
tickets cannot be advanced further without external testing, and what that testing needs to be.

## Update — 2026-09-17

Two changes to the picture above:

1. **This environment now has a working render backend — T-003 is unblocked.** Re-probed rather than
   assumed: `/dev/dri` is still absent, but `EGL_EXT_platform_device` (headless, surfaceless — no X11/
   Wayland/DRM needed) successfully initializes Mesa, and a real GLES 3.2 context renders
   (`GL_RENDERER: llvmpipe (LLVM 20.1.2, 256 bits)`). A parallel probe against `libvulkan.so.1` gets a
   `VK_SUCCESS` instance and enumerates one physical device (`llvmpipe`, `VK_PHYSICAL_DEVICE_TYPE_CPU`)
   — Lavapipe, Mesa's software Vulkan implementation. This is exactly the fallback path this document
   previously flagged as "worth trying first" (§T-003 above). **Important nuance: this is Mesa's CPU
   software rasterizer (llvmpipe/Lavapipe), not hardware GPU acceleration** — the host does appear to
   expose real GPU infrastructure to this WSL2 environment (`/dev/dxg` present, `libd3d12.so`/
   `libdxcore.so` under `/usr/lib/wsl/lib`, and a host driver DLL visible at
   `/mnt/c/Drivers/video/*/Graphics/libEGL.dll`), but the headless device-platform path this probe used
   only enumerated the software renderer, not that hardware. That distinction matters for two different
   tickets:
   - **T-003 (golden-image regression harness) is unblocked as designed.** It needs correct,
     bit-reproducible rendered frames to diff against goldens — a deterministic software rasterizer is
     actually a *better* fit for that than hardware, which can introduce vendor-specific rounding
     differences. Nothing about T-003's acceptance criteria requires real GPU hardware.
   - **T-006 / T-021 (bandwidth and frame-time measurement on reference mobile hardware) remain
     blocked.** llvmpipe/Lavapipe numbers are not representative of Adreno/Mali tile-based mobile GPU
     bandwidth behavior in any way — this backend answers "does it render correctly," not "is it fast
     enough on target hardware." Do not substitute this environment's timings for T-006/T-021.

   Practically: build the T-003 render step now, alongside the comparator logic already recommended
   below. `glslangValidator`/`spirv-cross` (used by T-002's compile gate) are not currently installed in
   this interactive session (only in the CI runner, via the workflow's own `apt-get install`) — they
   need to be installed here too before the render step can consume T-002's cross-compiled output.

2. **New scope: a legacy `.glslp`/`.glsl` preset pack is required alongside the `.slang` pack.**
   Until now this project targeted RetroArch's modern slang pipeline only (`.slangp`/`.slang`,
   Vulkan-semantics GLSL, cross-compiled per-backend via T-002's SPIR-V/spirv-cross gate). That pipeline
   does **not** produce a legacy-format shader as a side effect — RetroArch's older GLSL shader driver
   (`.glslp` preset + single-file `.glsl` with `#if defined(VERTEX)`/`#elif defined(FRAGMENT)`
   conditional compilation, `COMPAT_*` macros, non-Vulkan-semantics implicit uniform bindings) uses a
   structurally different file format from what spirv-cross's GL/GLES backend targets emit for the
   slang path, even though the underlying reconstruction math can be shared conceptually. This is now
   tracked as **T-040** in `docs/backlog.md`, requires its own root preset skeleton mirroring T-013, and
   needs the compile gate extended to validate the legacy format too (`glslangValidator` can check it
   directly with `-D VERTEX`/`-D FRAGMENT` defines against non-Vulkan GLSL semantics — confirmed
   feasible in principle against a real example file from `libretro/glsl-shaders`, not yet wired in).

## Update — 2026-09-17 (continued: render harness and legacy gate built)

Picking up directly from the update above in the same session:

- **T-003 is built**, not just unblocked. `tools/render_harness/` renders a `.slang` pass through the
  literal GLES cross-compile T-002's gate already validates (glslangValidator → SPIR-V →
  `spirv-cross --es`), against a real headless GLES 3.0 context (`egl_context.py`, ctypes against
  `libEGL.so.1` via `EGL_EXT_platform_device` — PyOpenGL's own EGL bindings don't cover the
  device-enumeration extensions this path needs, so context creation is hand-rolled and GL calls go
  through PyOpenGL once the context is current). `glslangValidator`/`spirv-cross` are now installed in
  this interactive session (confirmed on PATH, not just in the CI runner as previously noted) and
  `PyOpenGL`/`numpy`/`Pillow` installed cleanly via `pip3 --user --break-system-packages` — no sudo,
  no apt, needed for any of this. Verified end to end: the stub pass and the mobile-lite skeleton both
  render as byte-identical passthroughs of their source image, twice-rendered frames hash-identical
  (determinism), and deliberately corrupting a golden is correctly caught and reported with a
  mismatched-pixel-count/percentage and max-delta message. 55 goldens seeded for the
  `argus-mobile-lite` preset against the entire synthetic corpus (`tools/render_harness/goldens/`).
  **Not done:** actually rendering through GL-desktop, Vulkan, D3D11/12, or Metal — only GLES is
  executed; see T-003's backlog entry for exactly what's missing from each. Wired into CI as a second
  job (`render-harness`) in `.github/workflows/compile-gate.yml`.

- **T-040's compile-gate box is done**: `tools/compile_gate/compile_check_legacy.py` compiles every
  shipped legacy `.glsl` file's vertex and fragment stages directly (no SPIR-V step — the legacy
  driver isn't Vulkan-semantics GLSL) against GLES 300 (the actual T-005 target), desktop GLSL 150 and
  120, and GLES 100 (checked only because the file's own `COMPAT_*` macros claim `#if __VERSION__ >=
  130` support for it — not a real target, and labeled as such after an earlier draft of this script
  mislabeled it as "the T-005 floor," which it is not; T-005 floors this project at GLES 3.1+, not
  GLES 2.0). **Caught a real bug in the T-040 skeleton while building this**: the shared `TEX0`
  varying was declared before any GLSL ES default float precision existed, which GLSL ES's fragment
  stage requires before the first unqualified float declaration — glslangValidator rejected it
  outright. Fixed by moving `precision mediump float` before the shared declaration rather than
  leaving it inside the `FRAGMENT`-only branch (see the shader file's own comment, and the earlier
  header comment noting a *different*, already-fixed ordering issue in the same area — this is a
  second instance of the same class of bug, which suggests the general pattern is worth double-
  checking again once real reconstruction code adds more declarations to this file).

- **Found and fixed a second, unrelated bug while wiring T-040 into CI**: the existing
  `.github/workflows/compile-gate.yml` step that compiles shipped `.slang` passes used
  `shaders/**/*.slang` with only `shopt -s nullglob` set, not `globstar` — without `globstar`, bash's
  `**` behaves as an ordinary single-level `*`, so it silently matched nothing against the actual
  three-levels-deep `shaders/shaders_slang/argus/shaders/*.slang` path and the step has been printing
  "no shipped .slang passes yet" instead of actually gating shipped shaders since T-013 first landed.
  Fixed by adding `globstar`; confirmed locally that the corrected glob now matches. The equivalent
  legacy-`.glsl` CI step was added with `globstar` from the start.

## Update — 2026-09-17 (continued again: T-015/T-016 built, a GLES-version bug fixed)

- **T-015 and T-016 are built** — `tools/classifier_gpu/` (`classify_debug.slang`, `reference.py`,
  `verify_gpu.py`, `report.md`). The GLSL port of T-004's classifier surfaced real numerical bugs a
  CPU-only spike couldn't have: a 0/0-indeterminate checkerboard-autocorrelation ratio that CPU float
  arithmetic happens to cancel exactly but a GPU's different summation order doesn't (was producing
  false dither-positive noise on 77% of pixels in one test image), and a unique-color-count proxy
  that needed 32 luma bins instead of the 8 first tried, to resolve this corpus's own near-black
  glyph-outline/background pair. Both fixed and re-verified; see `report.md`'s six numbered findings
  for the full account, including two that are *not* bugs (a stroke-width raw-value divergence that
  never actually changes the final classification, and one corpus category that legitimately sits on
  a floating-point knife-edge at the dither threshold) — kept separate from the real fixes rather
  than blurred together, on the same "record honestly" principle this project has followed since
  T-004's own spike report.

- **Found and fixed a real bug while building T-015**: `bitCount()`, needed for the unique-color
  proxy, doesn't exist in GLSL ES 300 — it's an ES 3.10+ builtin. This exposed that `tools/
  compile_gate/compile_check.py`'s GLES backend target and `tools/render_harness/render_pass.py`'s
  GLES cross-compile were both hardcoded to `--version 300 --es`, silently *below* the GLES 3.1+
  floor `docs/gles-floor.md` (T-005) actually decided on for this project back in Phase 0 — a
  mismatch that had shipped unnoticed through T-013/T-040's skeletons and T-003's initial build
  because neither used any 3.1-only feature yet. Fixed by bumping both to `--version 310 --es`;
  confirmed this project's actual EGL context already negotiates ES 3.2 (`GL_SHADING_LANGUAGE_VERSION:
  OpenGL ES GLSL ES 3.20`), so 310 is what's actually being exercised, not just an aspirational
  target. `tools/compile_gate/compile_check_legacy.py`'s primary GLES profile was bumped to match for
  the same reason (kept GLES 300 as a secondary, informative-only check for legacy-driver consumers
  that may predate 3.1, since the legacy pack's audience is broader than this project's own device
  matrix). Re-ran the full T-003 golden set after the bump — all 55 tuples still match (the
  passthrough skeletons don't use any 3.1-only feature, so this was a pure toolchain-target fix, not
  a rendering change).

## Update — 2026-09-17 (continued once more: T-019 built)

- **T-019 is built** — `tools/dither_reconstruct/` (`dither_debug.slang`, `dither_reference.py`,
  `generate_soft_dither.py`, `verify_gpu.py`, `report.md`). Same verify-against-CPU-reference-through-
  the-real-render-harness pattern as T-015/T-016. The rule: each class-(b) pixel blends between its
  exact source color and its local 5x5-window mean color, by an amount that depends on both the FR5
  `ARGUS_DITHER_STRENGTH` parameter (0 at the default of 1.0 — full preservation for everyone) and a
  "hardness" signal derived from `spread` (the same statistic T-015's checkerboard-autocorrelation 0/0
  guard already computes) — a stark, high-contrast checkerboard degrades less than a soft, close-color
  dither at the same non-default strength setting, since averaging two very different colors produces
  an obviously-wrong muddy color rather than just "less crisp." All three T-019 acceptance criteria
  pass against the actual rendered shader output, not just the CPU model (`report.md`'s results table).

- **Found a real corpus gap while building this, not a bug**: T-019's third acceptance box wants
  measurably different behavior between "NES-style hard dither" and "SNES-style blending," but no
  existing T-008 corpus sample isolates the soft/close-color case — every existing dither sample
  (`checkerboard_transparency`, `dither_ramp`) uses high-contrast color pairs (measured `spread`
  ~17-76 luma units). Added `corpus/synthetic/dither_soft/` (new, additive test content scoped to
  this ticket, not a change to T-008) with a close-color (~20 luma units apart, measured spread 7.7)
  Bayer-dithered sample per system — see `report.md` Finding 1 for why this matches what
  `docs/requirements.md` §5 FR9 actually means by "SNES-style" (real alpha blending directly wouldn't
  be classified as dither at all; the case worth testing is SNES-era content that still uses ordered
  dithering, just between closer palette entries than NES/Genesis's typical high-contrast pairs).

- **Additive change to `tools/classifier_gpu/reference.py`**: exposed `spread` (already computed
  internally for the checkerboard-autocorrelation guard) as its own field in `compute_stats()`'s
  return dict, since T-019 needed it directly. Doesn't change T-015/T-016's already-verified behavior
  — pure exposure of an existing intermediate value, not a new computation.

## Update — 2026-09-17 (continued yet again: T-017 built, real classifier-separability limit found and tracked as T-041)

- **T-017 (text/glyph protection reconstruction rule) is built** —
  `tools/text_protect/` (`text_debug.slang`, `text_reference.py`, `verify_gpu.py`, `report.md`), same
  verified-through-the-real-render-harness pattern as T-015/T-016/T-019. The rule: class-(d) pixels
  output their exact source color (no interpolation, no strength dial the way T-019's dither rule
  has — FR2 asks for a hard guarantee here, not a tunable one); everything else falls back to the
  same local-mean placeholder T-019 uses for its own non-dither pixels. Checked against a real
  comparison baseline ("unprotected": no class-(d) special case at all) rather than only the
  trivially-true "protected == nearest-neighbour on protected pixels" claim — legibility measured
  0.651 with the routing on vs. 0.002 with it off, a substantive, not tautological, result.

- **Found, and did not paper over, a real pre-existing limitation while checking T-017's second
  acceptance box**: T-010's `text_negative` corpus (fur/hair, architectural grids, weapon-outline
  silhouettes) was deliberately built to share the same thin-high-contrast-stroke signature as real
  glyphs, specifically so an over-triggering classifier couldn't look like it was succeeding. Checked
  directly, per-statistic, whether any threshold on T-015's four wide-kernel statistics could separate
  them: **none can** — variance magnitude is close between real glyphs and weapon-outline art (both
  are just "high-contrast strokes on a flat background," which is what variance actually measures),
  and checkerboard-autocorrelation/popcount don't separate any pair either. Measured false-positive
  rate: 80.8%, unchanged from T-004/T-010's own original measurement — confirming this is real and
  inherited, not a regression from T-017's own work. Per this project's documented discipline (no
  checkbox checked without verification, no threshold "agreed" without evidence it's achievable), the
  false-positive acceptance box is left **unchecked** with the full evidence in `report.md`, and the
  actual fix is opened as **T-041**, a new ticket (`docs/backlog.md`), rather than silently absorbed
  into T-017 or asserted as passing. T-017's reconstruction rule itself is not implicated: nearest-
  preserving reconstruction is a safe (if suboptimal) fallback even when misrouted, unlike the
  destructive-smoothing alternative it protects real text from — this is argued and evidenced in
  `report.md`, not just asserted.

## Update — 2026-09-17 (continued once more: T-018 built, a real driver bug found and worked around, an honest non-win reported)

- **T-018 (LUT-topology edge reconstruction) is built** — `tools/edge_reconstruct/` (`edge_debug.slang`,
  `edge_reference.py`, `regenerate_lut_glsl.py`, `verify_gpu.py`, `report.md`), same
  verified-through-the-real-render-harness pattern as T-015/T-016/T-019/T-017. The rule: for classes
  (a)/(c), look up T-014's LUT topology/confidence, then blend each output pixel toward whichever
  source-texel neighbor lies along the estimated edge normal, weighted by the output pixel's sub-texel
  position — replacing nearest-neighbour's abrupt per-texel jump with a sub-pixel-accurate transition,
  and reducing to an exact no-op on flat art (confidence 0, no regression by construction, not a special
  case). Independently designed against T-014's own already-cleared generic LUT concept, not derived
  from any GPL/LGPL source (`docs/licensing.md`).

- **Found and isolated a real, reproducible Mesa/llvmpipe compiler bug** while bringing this shader up:
  a *dynamically-indexed* `texelFetch` on a *second* texture sampler (anything beyond `Source`)
  corrupted unrelated shader state for the whole frame, even inside a branch provably never taken.
  Root-caused via bisection (rendering intermediate values as color to narrow down the corruption) down
  to a 6-line minimal repro — see `report.md` Finding 1. Restructuring control flow did not fix it;
  swapping the LUT from a sampled texture to a generated GLSL `const vec3[256]` array (same 256 values,
  regenerated from T-014's own `generate_lut.py` by a new script, `regenerate_lut_glsl.py`) did.
  **This is a workaround scoped to this pre-fusion debug shader in this specific software-rasterizer
  environment** — T-014's texture design and T-020's real shipped pass should still use the baked
  texture as intended, and that path needs its own re-verification against a real GPU driver before
  either trusting or distrusting it based on this environment's bug.

- **Tried a plausible-sounding refinement that measurably made things worse, caught it, and reversed
  it**: scaling the reconstruction blend amount by LUT confidence (reasoning: less-clear topology should
  blend less) made sub-pixel edge accuracy *worse* than plain nearest-neighbour. Confidence is
  popcount/8 — how edge-like the local topology is — not a measure of directional certainty, so a real,
  clean diagonal edge (which commonly has confidence well under 1.0) still deserves a full geometric
  blend. Removed the scaling; fixed it (report.md Finding 2).

- **Reported an honest, non-passing result rather than a favorable cherry-pick**: an initial check at a
  single scale (4x) showed this rule beating Omniscale (1.051 vs. 1.110 mean sub-pixel error against the
  diagonal sweep's own analytic ground truth). Testing across every scale this tier would realistically
  run at (2x-6x) instead of just that one showed it only wins 1 of 5 — Omniscale wins by a similar
  margin at the other four. The "beats SABR and Omniscale" backlog box is left **unchecked** with the
  full per-scale table in `report.md`, rather than reported as passing on the one scale that happened to
  win. SABR itself was not run at all, consistent with T-011's own already-established position that
  even *running* SABR's unmodified code for comparison is gated on a human licensing-scope decision.

## Completed this session

| Ticket | What was built | Where |
|---|---|---|
| T-001 | Licensing posture for xBRZ/ScaleFX/SABR/Omniscale/HQx, sourced against the live libretro/slang-shaders repo | `docs/licensing.md` |
| T-002 | Cross-backend compile gate: stub `.slang` pass, glslang→SPIR-V→spirv-cross pipeline covering Vulkan/GL/GLES/HLSL/MSL, wired into CI | `tools/compile_gate/`, `.github/workflows/compile-gate.yml` |
| T-004 | Two-level classifier feasibility spike — **dither vs. AA-gradient separation passes (0.906, threshold 0.85)**, the ticket's explicit gate | `tools/classifier_spike/`, `tools/classifier_spike/spike_report.md` |
| T-005 | GLES floor decision: gather-only, no 3.0 fallback, sourced against real device GPU specs | `docs/gles-floor.md` |
| T-008 | Synthetic pattern generator: dither ramp, diagonal sweep (15-75° in 5° steps), glyph sheet, checkerboard-transparency, at 5 systems' native resolutions | `tools/patterns/generate_patterns.py`, `corpus/synthetic/` |
| T-009 / T-010 | Text legibility positive set (3 styles × 5) and false-positive negative set (3 categories × 5), both fully synthetic/redistributable | `tools/patterns/generate_text_sets.py`, `corpus/synthetic/text_positive/`, `corpus/synthetic/text_negative/` |
| T-012 | Perceptual A/B comparison harness — client-side, labeled/blind modes, JSON export | `tools/ab_compare/index.html` |
| T-014 | 256-entry 3×3 topology LUT, baked as RGBA8 texture + raw binary, symmetry/rotation invariants unit-tested | `tools/lut/generate_lut.py`, `tools/lut/lut_test.py`, `tools/lut/topology_lut.png` |

All of the above are independently re-runnable (`python3 tools/.../*.py`), have no dependency on a
GPU or physical device, and are committed with their generated output so CI/reviewers don't need to
regenerate to see results.

## Blocked on external testing

These backlog items cannot progress further inside this environment. Each needs something this
container structurally cannot provide (no `/dev/dri`, so no GPU/EGL/Vulkan context at all; no
network path to a specific physical device; no legal/community sourcing judgment call).

### T-003 — Headless golden-image regression harness
**Status: unblocked as of 2026-09-17 — see the Update section above.** A surfaceless
`EGL_EXT_platform_device` context against Mesa llvmpipe (GLES 3.2, confirmed by direct probe) and a
Lavapipe software Vulkan device (confirmed via `vkCreateInstance`/`vkEnumeratePhysicalDevices`) are
both reachable without `/dev/dri`. Neither is hardware-accelerated, but T-003's acceptance criteria
(byte-identical output across two runs, per-tuple pixel-delta diffing against committed goldens) call
for correctness/determinism, not mobile-representative performance, so a software rasterizer is a
legitimate implementation, not a workaround-with-caveats. Next step: build the render step (feed
T-002's cross-compiled backend output through the appropriate context — GL/GLES via EGL, Vulkan via
the Lavapipe ICD) and the PNG-diff/goldens-comparison logic together; both are buildable now.

### T-006 — Reference handheld bring-up and measurement methodology
**Blocked on: physically possessing a Retroid Pocket-class Android device.** This is inherently not
something a cloud container can do. No workaround — this needs a person with the hardware.

### T-007 — Redistributable content corpus (real homebrew/PD game captures)
**Blocked on: sourcing and legally vetting specific homebrew/public-domain ROMs/captures.** Unlike
T-008/T-009/T-010 (which this session solved by generating everything synthetically, sidestepping
the redistribution question entirely), T-007 specifically wants real captured game frames across
NES/SMS, SNES/Genesis, and GB/GBC/GBA homebrew titles. That requires picking specific titles,
confirming each one's actual license/redistribution terms individually, and capturing frames from a
running emulator — a curation judgment call better made with the project owner's input on which
homebrew scene titles to use, not guessed at. The synthetic corpus already built covers the same four
content categories called for in §8 (flat-color sprite art via the glyph/checkerboard patterns,
dithered transparency, gradient-adjacent content via the AA half of the dither-ramp pattern, and the
diagonal sweep standing in for fast-scrolling-parallax edge content) well enough to unblock T-004 and
Phase 1 classifier work; T-007's real-game corpus remains open for whenever specific titles are
chosen.

### T-011 — Catalog existing-shader failure cases
**Status: partially unblocked as of 2026-09-17.** The render-backend half of this ticket's blocker is
resolved (see the Update section above and T-003) — ScaleFX and Omniscale (both MIT, cleared for
direct execution per `docs/licensing.md` §2) can now actually be run against the corpus through the
same EGL/Vulkan software-rasterizer path. **Still blocked:** xBRZ/SABR/HQx remain no-go/conditional
for *execution* of project-controlled ports under T-001's clean-room determination — that half needs
either a licensing-scope decision (accepting GPL/LGPL obligations on specifically those comparison
runs) or continuing to characterize their failure modes from published documentation/screenshots
rather than by running project-controlled code, as already recommended. T-007's real-game corpus is
also still needed for full coverage; the synthetic corpus can unblock a first pass on ScaleFX/Omniscale
now.

## What "proceeding as far as possible" means from here

Everything in Phase 0 that's pure software — research, offline algorithm prototyping, compiler
tooling, synthetic content generation — is done. As of 2026-09-17, **T-003 is actually built**, not
just unblocked (see Update above): a shader pass can be rendered through a real GLES context and
checked against a committed golden in one command (`python3 tools/render_harness/run_harness.py`).
T-013 (slang skeleton) and T-040 (legacy skeleton) both exist as passthrough passes, both pass their
respective compile gates, and both are seeded with goldens. Phase 1 shader work no longer has to
proceed blind of visual feedback by default, and now doesn't have to build its own render harness
first either — that part is done. What's still genuinely stuck (T-006, T-007's real-game sourcing, the
copyleft half of T-011) needs a physical handheld or a human curation/licensing call — nothing left in
that set is a tooling gap.

**Next up on the critical path** (`T-001 → T-004 → T-016 → T-020 → T-023 → T-025 → T-033`): T-001,
T-004, T-015, T-016, T-017, T-018, and T-019 are all now built (see "Completed this session" above,
the README, and each ticket's own `tools/*/report.md`). **T-020 (fuse into a single shipped pass) has
no remaining Phase 1 ticket blocking it** — all three per-class reconstruction rules it needs
(T-017/T-018/T-019) exist and are individually verified. Two things are worth carrying into T-020
rather than treating as closed: **T-041** (class-(d) classifier separability, opened out of T-017's
report) and **T-018's honest non-win against Omniscale** (report.md Finding 2 — the compass-direction-
snapping hypothesis for the gap is untested and is the natural first thing to try if T-020's fused
result doesn't clear the Phase 1 exit bar's perceptual comparison, T-022). Neither blocks starting
T-020: T-017's report argues nearest-preserving reconstruction is a safe fallback even when misrouted,
and T-018's rule is verified correct and better than nearest-neighbour even though it isn't yet proven
to beat Omniscale specifically.

Recommended sequencing per ticket, now demonstrated five times (T-015/T-016, T-019, T-017, T-018):
implement against the passthrough skeleton, run `tools/compile_gate/compile_check.py` for portability,
verify against a `tools/*/verify_gpu.py`-style CPU-reference check through the actual render harness
(not just an offline CPU model) where the ticket has a numeric bar, then
`tools/render_harness/run_harness.py --update-goldens` once the rendered output is visually confirmed
correct (goldens are reviewable diffs in the commit, per T-003's third acceptance box — never update
them to paper over an unreviewed change) — though note T-015/T-016/T-019/T-017/T-018's debug/test
shaders were each verified through their own dedicated `verify_gpu.py` instead of the golden set,
since they're pre-fusion test shaders, not shipped passes; T-020 is what actually needs new goldens.
T-040's legacy pack should get the same treatment in parallel as each tier lands, not written after
the fact from finished slang passes. Watch for the same class of environment-assumption bug found
multiple times this session (GLES-300-vs-310, the CI globstar gap, and now T-018's dynamically-indexed
second-sampler Mesa/llvmpipe miscompilation — report.md Finding 1): re-check tool and driver
assumptions against what's actually true in this environment rather than trusting an earlier comment
or assuming a software rasterizer behaves like a real GPU driver. Also watch for the pattern T-019,
T-017, and T-018 all hit in different forms — a missing corpus category (T-019), an unachievable
acceptance threshold (T-017), and a result that only looked like a win at one cherry-picked scale
(T-018) — check what the acceptance criteria actually need, test broadly enough to know whether the
tooling/algorithm can actually deliver it, and when it turns out not to, say so and open new tracked
scope (T-040, T-041) rather than quietly loosening the bar or reporting the favorable case alone.

**Still open on T-003 itself**, tracked as unchecked in its backlog entry rather than left implicit:
GL-desktop execution (same EGL device, different API binding — small lift, not yet wired), a headless
Vulkan render path (distinct boilerplate from EGL/GLES, not started), and D3D11/12/Metal remain
compile-only since no runtime for either exists on this platform.

## Update — 2026-09-17 (continued once more: T-020 built — mobile-lite fused into a single shipped pass)

**T-020 is built.** `shaders/shaders_slang/argus/shaders/mobile-lite.slang` now fuses T-016's
four-class classifier with T-017/T-018/T-019's per-class reconstruction rules into the single
shipped pass FR3 requires — see `tools/fusion/report.md` for the full write-up. Summary:

- **Fusion verified exact**, not just "close": `tools/fusion/verify_gpu.py` checks the fused
  shader's output against each contributing debug shader (already independently verified by its own
  ticket) on content dominated by that class, and requires an exact match — result is 0-pixel
  difference across every class on every corpus sample tested, not a tolerance pass.
- **Compile gate passes clean** on all five backends (Vulkan, GL, GLES, D3D11/12, Metal).
- **Found and fixed a real gap in this project's own render-harness regression tests**, not a gap in
  the shader: `argus-mobile-lite.slangp` inherited `scale0 = 1.0` from T-013's passthrough skeleton,
  which made T-018's edge-reconstruction branch a mathematical no-op (sub-pixel offset is exactly 0
  at 1:1 scale) — the committed goldens were silently testing nothing of this ticket's actual logic,
  and reported a clean pass regardless. Fixed by setting `scale0 = 4.0` (real RetroArch playback is
  unaffected — `scale_type0 = viewport` means the runtime ignores `scale0` regardless; only this
  offline harness reads it literally) and regenerating all 60 goldens at that scale, each spot-checked
  visually against a plain nearest-neighbour upscale before committing. See `tools/fusion/report.md`
  Finding 1 for the full detail — this is the same class of "looked green, was checking the wrong
  thing" bug as the GLES-300-vs-310 mismatch and the CI globstar gap found earlier this session.
- Render-harness regression: 60/60 content/preset tuples now match their (regenerated, reviewed)
  golden at the corrected scale.
- Visual spot-check (manual, this session): edge reconstruction only measurably changes output near
  compass-aligned angles (matches T-018's already-documented compass-snapping limitation, not a new
  bug); dither/checkerboard content is exactly preserved at the default `ARGUS_DITHER_STRENGTH = 1.0`
  (correct per FR2); text/glyph interiors are untouched, only true edges change. No unexpected
  blurring or bleed into protected pixels.
- Verified from the compiled GLES reflection (not physical Adreno hardware, which isn't available in
  this environment — same limitation as T-006/T-021/T-018): exactly one `vec2` varying crosses the
  vertex/fragment boundary, trivially within any GLES 3.1 varying budget.

**Two things carried in from earlier tickets remain open, neither touched by this ticket**: T-041
(class-(d) classifier separability) and T-018's honest non-win against Omniscale (wins 1 of 5 tested
scales) — see `tools/fusion/report.md`'s "What's still open" for the full list, which also now
includes `textureGather` adoption (a tracked perf optimization, not attempted here) and T-014's
texture-vs-const-array LUT question (needs real GPU hardware to re-verify, carried from T-018
Finding 1).

**T-020 has no remaining Phase 1 ticket blocking it, and none of it blocks T-020 either now that it's
built** — `docs/backlog.md`'s T-020 boxes are updated accordingly. The mobile-lite tier's shipped
`.slang` pass is ready for a human to look at (`tools/fusion/report.md`'s visual spot-check table, or
by running the harness's rendered output directly) — this is the "shader ready for UAT" milestone.
**T-022 (Phase 1 exit validation — perceptual comparison against nearest-neighbour/SABR, bandwidth,
frame time, false-positive-rate threshold) has explicitly not been run** and is the next item on the
critical path; T-020's checks here are necessary but not sufficient for T-022's own bar. T-040's
legacy port of this fused logic also remains open, tracked but not blocking.

## Update — 2026-09-17 (continued once more: T-011 partially built — a real comparison set against Omniscale, with a documented glyph-preservation win)

Off the back of T-020 landing, built `tools/comparison/` (`generate_baselines.py`, `report.md`):
renders the full synthetic corpus through **argus-mobile-lite** (T-020's shipped pass), **Omniscale**,
and **nearest-neighbour** (the honest control) at matched 4x scale, into directories ready for
`tools/ab_compare/index.html` (T-012) or programmatic diffing.

**Headline finding**: on `glyph_sheet` content, argus-mobile-lite is pixel-identical to
nearest-neighbour (T-017's text/glyph protection working exactly as designed) while Omniscale
visibly rounds and anti-aliases glyph corners — the largest gap in the comparison table (9.721 vs.
0.000 mean-absolute-difference-from-nearest-neighbour) and a clear, visually legible result, not just
a number. The diagonal-edge sub-pixel accuracy comparison against Omniscale is not recomputed —
`tools/fusion/verify_gpu.py` already proves fusion didn't change T-018's edge-reconstruction output,
so T-018's existing 2x-6x win/loss table (wins 1 of 5) is cited directly rather than re-derived.

**Two things intentionally not done, both flagged rather than silently skipped:**
1. **ScaleFX** (MIT, cleared under T-001) is vendored (`tools/comparison/reference_shaders/scalefx/`)
   but not executed — it's a 6-pass filter chain with named cross-pass texture aliasing, and this
   project's render harness is single-pass only. Running it would need a real multi-pass filter-chain
   sequencer (the same category of work Phase 2's T-023/T-024 will eventually need), which wasn't
   improvised here — an unverified sequencer risks reporting misleading comparison numbers, worse than
   not having them.
2. **xBRZ/SABR/HQx** were not vendored or run at all — all three are copyleft with no permissive
   subset for direct execution (`docs/licensing.md`, T-001). This was this project's own conservative
   choice, not a decision the project owner had actually been asked to make and held up — see the
   2026-09-19 update below for the correction and what changed.

T-011 remains open (2 of 5 baselines actually run at time of writing), tracked honestly rather than
closed early.

## Update — 2026-09-18 (picking up an interrupted session: T-042 finished and committed)

The prior session ended mid-stream right after T-011 landed (`add9be9`), with `tools/eval_metric/`
already built on disk but untracked — never added to git, never given a ticket number, never written
up here. Picked back up, verified it rather than trusting it as-is (re-ran `run_eval.py`: reproduces
its own committed `report.md` table exactly, byte-for-byte, and a visual spot-check of
`audit/letter_g.png` matches the reported 90.2/90.8/91.6% numbers), and closed the loop: opened
**T-042** (new ticket, per this project's own convention for scope discovered mid-session rather than
folding it into T-011) and committed the tool.

**What T-042 adds over T-011's existing comparison set**: a standardized, reproducible ground-truth
metric (IoU of a binarized shape mask, from an 8x-supersampled-then-box-downsampled render) instead
of T-011's qualitative crop-comparison, covering shapes T-008's hand-drawn corpus and T-018's
diagonal-only analytic ground truth don't — a curve and two real letterforms.

**One real gap found while tying this up, not present in the code but in its own reporting**: the
tool's `report.md` is script-generated (`run_eval.py`'s `write_report()`) and, as left by the
interrupted session, presented only the raw score table with no interpretive read — exactly the kind
of "table with no honest read" gap this project has caught itself in before (T-018's initial
single-scale over-claim, before the full 2x-6x table showed the real 1-of-5 picture). Checked the
actual numbers before writing anything: **argus-mobile-lite loses to Omniscale on IoU for 3 of the 4
shapes (diagonal line, curve, letter A) and only wins on letter_g** — a more mixed picture than
T-011's headline glyph-preservation win alone suggests. Added a "Reading the result honestly" section
to `run_eval.py`'s generated report explaining the likely reason (Omniscale's smoothing costs it on
T-011's filled-glyph test but gains a small, consistent IoU edge on thinner supersampled strokes/
curves) and connecting it explicitly to T-018's own already-honest Omniscale non-win, rather than
letting the two honest-non-win findings sit undiscovered in two different reports. Regenerated
`report.md` after the edit and confirmed the score table itself is unchanged (only the new prose
section was added).

No other loose ends found from the interrupted session — `git status` showed only this one untracked
directory, nothing half-edited elsewhere, and the branch (`phase1/t003-render-harness-t040-legacy-pack`,
7 commits through `add9be9`) was already pushed to `origin` in the meantime (see this repo's memory
for the SSH-key/`workflow`-scope auth story, not repeated here). This T-042 work is commit
`168a03b` on the same branch; PR still not opened.

## Update — 2026-09-19 (T-043: an analytical B/px lower bound, and a real concern for T-022)

With T-042 closed out and no other loose ends from the interruption, moved to the next item on the
critical path: **T-022** (Phase 1 exit validation), which depends on T-021 (measured bandwidth), which
is itself blocked on T-006 (physical reference handheld — still no device in this environment). Rather
than stop there, noticed T-006's own acceptance criteria already call for a *calculated* B/px to
validate a future real measurement against ("a known 2-pass shader measures within ±15% of its
calculated B/px") — that calculated number is hardware-independent and didn't exist yet anywhere in
this project. Built it as **T-043** (new ticket, new scope): `tools/bandwidth_estimate/
calculate_bpx.py` hand-accounts mobile-lite.slang's actual texture-read pattern (cited by line number
in the script, same rigor as `tools/edge_reconstruct/edge_reference.py`'s hand-ported CPU model) and
computes an ideal-cache (compulsory-misses-only) amortized bandwidth lower bound across the same
2x-6x scale range T-018 already established as realistic for this tier.

**Real finding, not just tooling**: at every scale in that range, the lower bound already exceeds §6's
8 B/px mobile-lite ceiling — 15.1 B/px at 6x, up to 40 B/px at 2x — even under the most generous
plausible caching assumption a static analysis can make. This traces directly to what "mobile-lite = 1
output-resolution pass" (FR3) structurally requires: the shipped shader's full 5×5 classification
kernel runs once per *output* pixel, not once per *native* pixel, because there's no separate
native-resolution pass (that's exactly what Phase 2's T-023 adds, at the cost of a second pass) to run
it in once and reuse the result. Checked this wasn't an artifact of the analysis before writing it up:
the edge-reconstruction branch's extra fetches (topology neighbors + directional blend sample) are all
within the classification kernel's own ±2-texel footprint, so they don't change the unique-texel
accounting — the 5×5 kernel alone already drives the whole result, at every branch.

**Reported as a caveated lower bound, not a conclusion T-022 has failed** — this is exactly the kind
of finding this project's docs discipline exists to catch honestly rather than let an untested
"looks fine" assumption carry forward into T-022 (the same shape of catch as T-018's honest Omniscale
non-win and T-042's own more-mixed-than-headline IoU result). Real hardware could still do better than
the idealized sliding-window cache model assumes — tile-based mobile GPUs are often good at exactly
this kind of small local-stencil reuse — but cannot do worse than this floor, so the gap (2-5x over
budget depending on scale) is large enough to be worth flagging now rather than waiting for T-006's
hardware to discover it. **T-022 should not be treated as a pass on the ≤8 B/px criterion without
either real measurement evidence or a design change**, and this is now on record in both T-021's and
T-022's own backlog entries for whoever picks this up next.

Committed alongside this write-up (`777e486`) and pushed.

## Update — 2026-09-19 (continued: T-044 — a small, real, well-understood text regression found)

Kept pulling the T-022 thread. T-042's own headline table has a number worth explaining rather than
citing at face value: argus-mobile-lite scores *below* nearest-neighbour on IoU for `letter_A` (94.0%
vs 94.2%) — surprising, since T-017/T-020 established pixel-identical output on T-010's own text
corpus. Built `tools/eval_metric/text_legibility_diff.py` to find out why rather than guess: splits
every argus/NN disagreement pixel into "boundary" (nearest-neighbour's own blocky upscale already
disagrees with ground truth there — an inherently ambiguous anti-aliased zone, not a regression) and
"interior" (NN matches ground truth, argus doesn't — the bucket that would actually mean a legibility
regression against the naive baseline).

**Result, opened as T-044**: a real but small and well-localized regression — 174 px on `letter_A`,
215 px on `letter_g` (~0.1-0.6% of the image), all of them genuinely wrong against ground truth where
NN is right. Before writing this up as either "nothing" or "a real problem," visually audited where
those pixels actually fall (`tools/eval_metric/audit/letter_*_legibility_regression.png` — wrong
pixels painted red on ground truth): every single one sits exactly on a curved stroke or sharp corner
(the A's apex and inner-triangle corners; the g's bowl curve and terminal), never in a flat interior
region. That location pattern matches **T-018's own already-documented compass-snapping limitation**
(the topology LUT's 8 discrete directions approximate a continuous curve or off-compass angle
imperfectly) showing up on a different corpus (T-042's anti-aliased letterforms) rather than a new,
unrelated bug — checked this against T-018's report before concluding it, not just eyeballed.

**Left an honest gap deliberately, not resolved here**: whether sub-pixel corner rounding on a large
supersampled test glyph constitutes a real *readability* problem for the small pixel-art text FR2/
T-017 actually targets is a judgment call this metric can't make on its own — recorded as open in
T-044 rather than asserted either way. Updated T-022's own "text legibility no worse than
nearest-neighbour" box to point at this finding rather than let it be assumed to pass by citing
T-011's pixel-identical result alone; both are real and need to be read together.

**Where T-022 actually stands now, after two sessions of digging into its dependencies without
hardware**: two of its six exit-criteria boxes now have concrete, hardware-independent evidence
against a clean pass (T-043's bandwidth lower bound already over budget; T-044's small text
regression), one depends on a licensing call still pending with the user (SABR, T-011), and the
frame-time/false-positive-rate/goldens-coverage boxes are untouched this session. T-022 itself should
not be run and checked off as if these were formalities — they're real, documented, open questions.
Committed (T-044's tooling + this write-up) and pushed.

## Update — 2026-09-19 (continued: T-045 — a real bug in T-040's foundation, caught before it shipped)

With T-022's dependencies as investigated as they can get without hardware or a licensing decision,
turned to T-040 (legacy `.glslp`/`.glsl` pack) — real, unblocked Phase 1 scope, still open. Before
porting T-020's actual math into the legacy skeleton, checked how the file's compiled GLSL version
actually gets decided by a real RetroArch install, rather than assume the existing skeleton (built
2026-09-17, currently a passthrough) already had this right. Fetched RetroArch's real legacy driver
source directly (`gfx/drivers_shader/shader_glsl.c` from github.com/libretro/RetroArch@master, via
`gh`/`curl`) and read `gl_glsl_compile_shader()` rather than rely on the previous session's header-
comment claims about it.

**Found two real, structural problems, both fixed before any reconstruction logic touched the file:**

1. The skeleton had **no `#version` line at all**. RetroArch's driver only substitutes a version when
   the file declares one itself; with none present, none is injected, and the file compiles under the
   implicit GLSL ES 1.00 default — incompatible with `texelFetch`/`in`/`out`/`bitCount` outright, which
   the real ported logic needs (same functions T-015's port already needed ES 3.10 for).
2. Even declaring *some* version wouldn't have been enough. The real driver remaps a declared version
   on GLES3-capable targets: `[130, 330)` maps to `"300 es"`, exactly `330` maps to `"310 es"`, `>330`
   maps to `"320 es"`. This project's own T-005 floor needs ES 3.10 specifically (`bitCount()`) — so
   the file must declare **exactly** `#version 330`, not the `130` its own COMPAT_* macros merely
   check for. Declaring 130 (the seemingly-safe, more-conservative choice) would have silently capped
   real mobile hardware at "300 es" and failed to compile the ported logic later — the exact shape of
   bug this project has now caught four times (GLES-300-vs-310, the CI globstar gap, T-018's Mesa
   texelFetch miscompilation, and now this) — each time by checking real tool/driver behavior instead
   of trusting an existing comment or assumption.

**Fixed, not just diagnosed**: `mobile-lite.glsl` now declares `#version 330` as its literal first
line (with the full remap table and source citation in a header comment), and
`tools/compile_gate/compile_check_legacy.py` was rewritten to simulate the real remap instead of
externally forcing a version line in front of the file's own text (which both misrepresented real
driver behavior *and* stopped being syntactically valid the moment the file declares its own
`#version` — GLSL forbids two). Verified the corrected gate passes clean on both real gating targets
(desktop verbatim, GLES3.1+ remapped) for the still-passthrough skeleton, and confirmed nothing else
regressed: the slang compile gate and all 60 render-harness goldens still pass unchanged (this work
touched only the legacy pack).

**Deliberately stopped here, not pushed further into the actual math port**: T-040's real logic port
(fusing T-020's classifier + reconstruction rules into this now-correctly-versioned file) and a
legacy-pipeline render harness (to verify golden parity against the slang pass, T-040's own still-open
acceptance box) remain open, tracked under T-040 itself. Building those on top of a freshly-fixed
foundation without room left to verify them with the same care T-015-T-020 each got would risk
shipping something that looks done but isn't — opened as **T-045** (the foundation fix, complete and
verified) rather than folded into a rushed, incomplete attempt at T-040's full scope.

## Update — 2026-09-19 (continued: T-011 — SABR, ScaleFX, and xBRZ actually running)

**Correction first**: the 2026-09-18 update above says xBRZ/SABR/HQx execution was "asked the user
directly" and left pending. The user corrected this directly in conversation — that framing was wrong;
it was this project's own conservative choice not to vendor copyleft source without checking first, not
a decision that had actually been put to the user and held up. The user then gave explicit direction to
proceed. Corrected in place above rather than left standing.

**What changed**: SABR (GPLv2+) and xBRZ (GPLv3, embedded) source was fetched directly from
`github.com/libretro/slang-shaders` (via `gh`/`curl`) to a scratch location *outside this repo* —
running them for comparison doesn't require permanently vendoring GPL source into this project's own
git history, so only their rendered *output* is committed, matching how `tools/comparison/renders/`
was already `.gitignore`d as regeneratable before this session. SABR turned out to be genuinely
single-pass (`shaders = 1`) — directly runnable through the existing `render_pass.py`, no new
infrastructure needed. xBRZ and ScaleFX (already vendored MIT, previously blocked — see 2026-09-17's
update above) both needed a real multi-pass filter-chain sequencer, which didn't exist yet; built one
(`tools/render_harness/render_multipass.py`).

**Building the sequencer surfaced real bugs, all found before trusting any output — verified via
per-channel spatial standard deviation, not just eyeballing, after an early pass that looked flat
turned out to have real per-channel variance hiding inside a flattened global min/mean/max (a
diagnostic mistake caught and corrected before drawing conclusions from it):**
1. **ScaleFX's own vendored `.slangp`/`stock.slang` layout was wrong** — the preset's unmodified
   `../../stock.slang` reference needs the file two directories up, but the previous session's fetch
   placed it only one up. Never caught because ScaleFX was never actually executed before now. Fixed
   by placing an identical copy (`tools/comparison/stock.slang`) where the unmodified preset actually
   expects it, rather than editing vendored file contents.
2. **`#pragma parameter` defaults were never being set for third-party passes** — real RetroArch
   always initializes these to their declared default; leaving them at GL's implicit `0` made
   ScaleFX's `scalefx-pass1.slang` divide by zero (`params.SFX_CLR`, default `0.50`), producing NaN
   across the whole frame. Fixed by parsing and setting each pass's own declared defaults
   (`render_pass.py`'s existing `parse_pragma_parameter_defaults`, already built for T-020).
3. **The push-constant block's instance name isn't consistent across real third-party shaders** —
   `params` in ScaleFX/xBRZ/SABR/the shared bicubic passes, `registers` in HQx. Grepped every fetched
   pass to confirm rather than assume one convention; the sequencer now tries both.
4. Same directory-depth vendoring bug as #1 recurred for xBRZ/HQx's shared `../../interpolation/`
   reference — same fix (place a copy at the depth the unmodified preset expects).

**SABR and xBRZ now render correctly and are visually confirmed sane** (real per-channel spatial
variance, and visual inspection matches each algorithm's known character — SABR's moderate edge
interpolation, xBRZ's stronger rounding). **HQx was attempted last and set aside**: it renders without
a crash through the same sequencer but produces a visibly wrong (near-black) result from a remaining
bug not yet isolated. Given HQx is also the most legally marginal of the three per `docs/licensing.md`
("conditional; default to no-go") and three of four previously-blocked baselines were already newly
unblocked, further debugging was deprioritized rather than open-endedly pursued — recorded honestly as
attempted-but-unresolved, not silently dropped.

**Content and comparison**: rather than only extend the existing synthetic corpus, built RPG-specific
content per the user's direct request (`tools/comparison/generate_rpg_text.py` — a bordered dialogue
box with two lines of body text, and a sheet of individual letterforms, both at native SNES-class
256x224 resolution) and rendered it through all six now-available baselines (nearest-neighbour,
Omniscale, SABR, ScaleFX, xBRZ, argus-mobile-lite — `tools/comparison/generate_rpg_baselines.py`).
Published as an Artifact for visual inspection: https://claude.ai/artifact/QgL8kSGvzWtwo94eksnJGU —
argus-mobile-lite keeps text pixel-crisp (T-017 working as designed); Omniscale and xBRZ visibly round
glyph corners and box edges at this native scale; SABR sits between the two.

**What this does and doesn't settle for T-011's own boxes**: "every corpus item rendered through all
five baselines" is now 4 of 5 executable (SABR/ScaleFX/xBRZ/Omniscale; HQx still blocked, now on a
technical bug rather than licensing) — a real improvement from 2 of 5, but **the newly-unblocked three
have only been run against this session's new RPG content, not yet against the full existing synthetic
corpus** (`dither_ramp`, `checkerboard_transparency`, `diagonal_sweep`, `text_positive`/`text_negative`,
`glyph_sheet`) the way Omniscale/nearest-neighbour already have via `generate_baselines.py`. Extending
`generate_baselines.py` itself to include SABR/ScaleFX/xBRZ across that full corpus is real, tracked,
not-yet-done follow-up work, not silently folded into "done" here.

## Update — 2026-09-19 (continued: a real orientation bug in the sequencer, and an honest numeric comparison)

**The user caught a real, serious bug the moment they looked at the published comparison**: ScaleFX's
output was rendered upside down. Their words: *"I think your assessment is properly bogus. Scalefx is
rendered upside down and backwards."* They were right, and the root cause was worth understanding
precisely rather than patched blind.

**Root cause**: `render_multipass.py` used the same fixed vertex quad for every pass, which assumes
its `Source` input is a freshly-uploaded, top-down (PNG-convention) texture. That's only true for the
very first pass — every later pass's `Source` is actually a *previous pass's own FBO*, which OpenGL
stores bottom-up (a fixed rasterizer fact: clip-space y=-1 always lands at the render target's row 0,
opposite a directly-uploaded texture's row 0). Each pass through the same quad therefore flips the
image's vertical convention relative to its input — meaning a chain's final orientation depended on
whether it had an even or odd number of passes, not on anything real. ScaleFX (6 passes, even) came
out upside down; xBRZ (3 passes, odd) happened to come out correct by accident, which is exactly why
the earlier "both look fine" visual check didn't catch this — it only checked xBRZ and SABR/ScaleFX's
letters spot-check, not the actual published dialogue-box render carefully enough.

**Fixed**: negate the Y row of the MVP matrix for every pass except the last, keeping every
intermediate FBO in the same top-down convention the next pass already assumes, so only the final
pass's existing (separately-correct) readback flip is needed — exactly matching how the already-proven
single-pass path works. Verified by regenerating both scenes for both affected baselines (ScaleFX,
xBRZ) and visually confirming correct orientation, text reading in the right line order, and glyphs
right-side up. Confirmed the bug was isolated to `render_multipass.py` only — T-042 through T-045
never touched that code path.

**Then built the numeric comparison the user actually asked for**, rather than continuing to lean on
visual impressions: `tools/eval_metric/rpg_text_eval.py`, same supersample-then-downsample
ground-truth method as T-042, applied to the RPG dialogue box and letters across all six baselines.
**Result, stated plainly**: xBRZ scores highest on both scenes (87.6%, 94.3%), SABR and ScaleFX both
beat argus-mobile-lite on both scenes, and **argus-mobile-lite is within noise of plain
nearest-neighbour** (82.0% vs 82.0%; 89.0% vs 88.3%). The user's own read — *"I think our renderer is
the worst and probably omniscale or xbrz is the best"* — is numerically correct for xBRZ specifically,
and close to correct more broadly: on this ground-truth-overlap metric, argus-mobile-lite does not
beat any of the three newly-available baselines, and barely distinguishes itself from doing nothing.
This is consistent with, not contradicted by, T-011's original `glyph_sheet` finding (argus pixel-
identical to nearest-neighbour, Omniscale visibly rounding corners) and T-042/T-044's own honest
non-wins — argus-mobile-lite's nearest-preserving text strategy has a real, separately-documented
upside (crispness) that simply does not show up as a ground-truth IoU win. Both are true; only one was
being said out loud before.

Republished the visual comparison with corrected renders and the numeric table folded in:
https://claude.ai/artifact/QgL8kSGvzWtwo94eksnJGU.

**Also written**: `docs/retroarch-testing.md` — the actual shader pack (`shaders/shaders_slang/argus/`)
already compiles clean on all five backends and needs no further work to drop into a real RetroArch
install; this just documents install/load steps and how to pull SABR/ScaleFX/xBRZ from RetroArch's own
bundled shader library for a real side-by-side, plus states the numeric result above up front so
manual testing starts from an accurate expectation rather than the earlier, too-favorable framing.
