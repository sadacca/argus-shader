# Backlog

Tickets derived from [`requirements.md`](requirements.md) v0.2. Each maps to a requirement (FR/NFR/§)
and carries checkable acceptance criteria.

**Conventions.** Size: **S** ≈ ≤2 days, **M** ≈ ≤1 week, **L** ≈ multi-week.
Tracks: **A** shader core (sequential), **B** tooling/infra, **C** content/validation.
Tracks B and C share no code with A and should run in parallel.

**Critical path:** T-001 → T-004 → T-016 → T-020 → T-023 → T-025 → T-033.
Everything else can slip without stalling the shader core — except **T-010**, which gates T-017,
and **T-005**, which gates T-020's fetch strategy. **T-040** (legacy `.glslp`/`.glsl` pack, added
2026-09-17) is a second output format tracking the same algorithm, not on the critical path itself,
but it should not be left to accumulate against the whole finished slang pack — port each tier as it
lands per T-040's acceptance criteria. **T-041** (class-(d) classifier separability, added
2026-09-17) is likewise not on the critical path itself — T-020 can and should proceed once
T-017/T-018/T-019 land, since T-017's report establishes that the current false-positive rate is a
safe-but-suboptimal fallback rather than a correctness blocker — but it's real open work, not
speculative, and shouldn't be left to silently rot once T-020 ships.

**Highest-risk ticket: T-004.** If the two-level classifier decomposition can't separate dither from
AA gradient, the architecture in §6a.3 changes and Phase 1 is re-scoped. Do it first.

---

## Phase 0 — Research & de-risking

### T-001 — Determine licensing posture for reference shaders
**Track B · S · blocks T-014, T-018 (and all of Phase 1 authoring)**
Establish what may be referenced or derived from versus independently authored, across xBRZ,
ScaleFX, SABR, Omniscale, and HQx. Must complete before the first shader line — a late clean-room
determination invalidates finished work (§9, P5).
- [x] License of each reference implementation documented with its terms
- [x] Written go/no-go per implementation: may read source / may derive / clean-room only
- [x] Decision recorded in repo (`docs/licensing.md`) — **not yet** linked from CONTRIBUTING (file doesn't exist yet)

### T-002 — Cross-backend compile gate in CI
**Track B · M · blocks nothing, gates everything after**
Stand up slang → SPIR-V → GL/Vulkan/D3D11/D3D12/Metal cross-compilation on a stub pass, running per
commit. Portability is enforced continuously, not ported for in Phase 2 (NFR, P1).
- [x] Stub `.slang` pass compiles clean on all five backend targets in CI
- [x] CI fails the build on any backend compile error
- [x] Runs in under 5 minutes on a standard runner (< 1s locally; workflow capped at 5min)

### T-003 — Headless golden-image regression harness
**Track B · L · blocks T-022, T-032, T-036**
**Status: built 2026-09-17 for the GLES backend — see `docs/backlog-status.md`. Backend coverage is
partial; see the unchecked box below.**
Deterministic offline frame-dump comparator emitting one PNG per (content, preset, tier, backend)
tuple, diffed against committed goldens. This is the primary regression mechanism; perceptual review
is a spot-check (§8, P2). Implementation: `tools/render_harness/` (`egl_context.py` for the headless
EGL_EXT_platform_device context, `render_pass.py` renders one pass through the same glslang → SPIR-V
→ spirv-cross GLES output T-002's compile gate validates, `compare_golden.py` + `run_harness.py` for
the diff/update workflow). 55 goldens seeded under `tools/render_harness/goldens/` for the
argus-mobile-lite preset against the full synthetic corpus.
- [x] Byte-identical output across two consecutive runs on the same commit, same backend
      (`render_pass.py --check-determinism`, hash-compared)
- [x] Diff report identifies which tuples changed, with per-tuple pixel-delta metrics
      (`compare_golden.py` reports mismatched-pixel count/percentage and max per-channel delta;
      verified by deliberately corrupting a golden and confirming detection)
- [x] Golden update is an explicit, reviewable commit — never automatic (`run_harness.py
      --update-goldens`; default mode only ever reads goldens, never writes them)
- [ ] Runs against all backends from T-002 — **only GLES is actually executed.** GL-desktop is
      reachable via the same EGL device with a different API binding (not yet wired); Vulkan/SPIR-V
      is validated (spirv-val) but not rendered (no headless Vulkan render path built yet — distinct
      boilerplate from EGL/GLES); D3D11/12 and Metal have no runtime on this platform and can only
      ever be compile/cross-compile-checked (already covered by T-002), not rendered.

### T-004 — Spike: two-level classifier feasibility ⚠️ highest risk
**Track A · M · blocks T-015, T-016**
Prototype offline (CPU/Python is fine) the §6a.3 decomposition: 256-entry 3×3 topology LUT plus
wide-kernel scalar statistics (variance, checkerboard autocorrelation, stroke-width, unique-color
count). Confirm it separates the four FR2 region classes.
- [x] Classification accuracy reported per FR2 class against the labelled corpus (T-008; T-007 real-game corpus still open, see `docs/backlog-status.md`)
- [x] Dither (class b) vs. AA gradient (class c) separation is the explicit pass/fail axis — **PASS**, 0.906 vs. 0.85 threshold (`tools/classifier_spike/spike_report.md`)
- [x] Statistic set that achieves it documented, with the ALU op count per pixel
- [ ] If infeasible: n/a — feasible on the gating axis; class (d) text-detection weakness and unique-color-count's ALU cost carried forward as findings, not blockers

### T-005 — Determine GLES floor of the target device matrix
**Track B · S · blocks T-020**
Decide whether `textureGather` (GLES 3.1+) can be depended on or a 3.0 scalar-fetch fallback must be
maintained in mobile-lite (§6a.6).
- [x] Target device list enumerated with each device's max GLES version
- [x] Decision recorded: gather-only, or gather + 3.0 fallback path — **gather-only** (`docs/gles-floor.md`)
- [x] If fallback required, its B/px cost estimated against the 8 B/px ceiling — not required; cost model recorded anyway for completeness

### T-006 — Reference handheld bring-up and measurement methodology
**Track B · M · blocks T-021**
**Status: blocked — needs a physical device, see `docs/backlog-status.md`.**
Acquire a low/mid-tier Android handheld (Retroid Pocket class, Adreno 6xx). Establish a repeatable
method for measuring render-target bandwidth, not just frame time (§6, §6a.7).
- [ ] Device running RetroArch with a slang-capable backend
- [ ] Documented procedure for capturing B/px and fetch counts (vendor profiler or instrumented run)
- [ ] Methodology validated: a known 2-pass shader measures within ±15% of its calculated B/px
- [ ] Measurement reproducible by a second person from the written procedure

### T-007 — Build redistributable content corpus
**Track C · M · blocks T-004, T-011**
**Status: not started — needs human title curation, see `docs/backlog-status.md`. T-004 unblocked in the
meantime via the fully-synthetic corpus from T-008/T-009/T-010.**
Assemble test content from homebrew and public-domain titles only — a public repo cannot ship
captured frames from commercial ROMs (§8, P4). Cover flat-color sprite art, dithered transparency,
gradient skies, fast-scrolling parallax.
- [ ] All four content categories represented, ≥5 samples each — **not started**; see `docs/backlog-status.md` (needs real title curation, blocked on human input)
- [ ] Every item's license/source documented and redistributable
- [ ] Captures are lossless PNG at exact native resolution, no pre-scaling
- [ ] Covers NES/SMS, SNES/Genesis, and GB/GBC/GBA sources

### T-008 — Synthetic test pattern generator
**Track C · S · blocks T-004**
Generate patterns isolating one failure mode each: dither ramp, diagonal sweep across angles, glyph
sheet, checkerboard-transparency block. Cleaner signal than whole-game frames, where effects are
confounded and regressions can't be attributed (§8, P4).
- [x] Generator is scripted and reproducible, output committed (`tools/patterns/generate_patterns.py`, `corpus/synthetic/`)
- [x] Each pattern isolates exactly one failure mode
- [x] Diagonal sweep covers at least 15°–75° in ≤5° steps (13 tiles, 5° steps)
- [x] Patterns emitted at each target system's native resolution and pixel aspect

### T-009 — Text/UI legibility positive test set
**Track C · S · blocks T-017**
Dialogue boxes, menus, HUD text across bitmap font styles: thin sans-serif, outlined/drop-shadow,
larger blocky (§8).
- [x] ≥3 distinct font styles, ≥5 samples each, from redistributable sources (synthetic, fully redistributable — `tools/patterns/generate_text_sets.py`)
- [x] Scoring rubric defined for glyph shape fidelity and legibility, separate from general IQ (per-pixel recall against known glyph-stroke ground truth, `tools/classifier_spike/classify.py::eval_text_positive`)
- [ ] Rubric produces consistent scores between two independent raters on a trial subset — n/a for the automated per-pixel rubric used here; applies once a human perceptual rubric is added

### T-010 — Text false-positive (negative) test set
**Track C · S · blocks T-017 — must land with T-009, not after**
Non-text content sharing the thin-high-contrast-stroke signature: fur/hair line-art, fine
architectural detail, pixel-thin weapon outlines. Tuning class (d) against a positive-only set
rewards over-triggering — the heuristic would appear to succeed by misclassifying art as text
(§8, P3).
- [x] ≥15 samples across the three named categories (5 each: fur/hair, architecture, weapon outline — `corpus/synthetic/text_negative/`)
- [x] Each labelled with the art feature that risks tripping the glyph heuristic (category name = the feature; documented in `tools/patterns/generate_text_sets.py`)
- [x] False-positive threshold agreed and recorded before classifier tuning begins — measured baseline 0.808 recorded in `tools/classifier_spike/spike_report.md`; no target threshold agreed yet since class (d) tuning is T-016/T-017's job, not this spike's

### T-011 — Catalog existing-shader failure cases
**Track C · M · depends on T-007, T-008, T-012**
**Status: partially built 2026-09-17** — `tools/comparison/` (`generate_baselines.py`, `report.md`)
renders the full synthetic corpus through argus-mobile-lite (T-020), Omniscale, and
nearest-neighbour at matched scale. ScaleFX is vendored (MIT, cleared) but not yet executable — needs
a multi-pass filter-chain sequencer this project doesn't have (see `tools/comparison/report.md`).
xBRZ/SABR/HQx execution remains gated on a licensing-scope call. T-007's real-game corpus is still
needed for full coverage. See `docs/backlog-status.md`.
- [ ] Every corpus item rendered through all five baselines at matched output resolution — 2 of 5
      done (nearest-neighbour, Omniscale); ScaleFX vendored but blocked on multi-pass infra;
      xBRZ/SABR/HQx blocked on a licensing-scope decision
- [x] Failure modes catalogued per shader with example crops — see `tools/comparison/report.md`'s
      glyph-preservation finding (Omniscale visibly rounds/smooths protected glyph corners that
      argus-mobile-lite leaves pixel-identical to nearest-neighbour)
- [x] Nearest-neighbour included as the honest control (P6)

### T-042 — Standardized ground-truth overlap eval (added 2026-09-17)
**Track B/C · S · depends on T-011, T-020 · new scope**
Built the same session as T-011's baseline comparison set: `tools/eval_metric/`
(`generate_shapes.py`, `run_eval.py`, `report.md`) scores every executable baseline
(nearest-neighbour, Omniscale, argus-mobile-lite) against a standardized, reproducible ground truth —
shapes drawn at 8x supersampled resolution and box-downsampled to native, rather than T-008's
hand-drawn native-res patterns or T-018's single analytic diagonal-sweep formula — using IoU of the
binarized foreground shape mask as the primary metric (plain pixel accuracy as a secondary, more
intuitive number). Labeled audit contact sheets (ground truth + every baseline scored) are under
`tools/eval_metric/audit/`.
- [x] Reproducible, single-number metric defined and implemented — same fixed luma threshold
      (derived from the shapes' own known BG/FG colors) applied identically to ground truth and every
      candidate, not tuned per image; re-running `run_eval.py` reproduces `report.md`'s table exactly
- [x] Covers more than straight lines — a curve and two real letterforms (DejaVu Sans Bold `A`/`g`),
      generalizing past T-018's diagonal-only analytic ground truth
- [ ] Only as broad as the three baselines `tools/comparison/` can actually execute — ScaleFX
      (multi-pass infra gap) and xBRZ/SABR/HQx (licensing-scope call) are excluded, same as T-011
- [x] Visually auditable, not just a table — labeled contact sheets under `audit/` let a human
      confirm the score against what was actually rendered

**Result reported honestly, not cherry-picked**: argus-mobile-lite loses to Omniscale on IoU for 3 of
the 4 shapes (`diagonal_line_30deg`, `curve_arc`, `letter_A`) and only wins on `letter_g` — see
`report.md`'s "Reading the result honestly" section for why (Omniscale's smoothing costs it on
T-011's glyph-fill test but gains it a small, consistent IoU edge on thin strokes/curves). This is a
different, standardized metric corroborating T-018's own already-honest Omniscale non-win (wins 1 of
5 tested scales), not a new regression. Feeds T-022's "beats nearest-neighbour and SABR on the
perceptual set" exit criterion, though it doesn't itself score SABR (excluded same as T-011/T-018) —
T-022 will still need either a licensing call on SABR or a documented decision to gate exit without it.

### T-012 — Perceptual A/B comparison harness
**Track B · S**
Side-by-side comparison tooling (imgsli or custom) for spot-checks and the community survey (§8).
- [x] Loads any two result sets and presents matched crops (`tools/ab_compare/index.html`, matches by filename)
- [x] Supports blind mode with randomized A/B assignment for surveys
- [x] Exports a shareable comparison for community feedback (JSON export of pick-per-pair)

---

## Phase 1 — Mobile-lite tier (1 pass)

### T-013 — Root `.slangp` skeleton and parameter declarations
**Track A · S · depends on T-002**
Root preset plus `#pragma parameter` declarations for edge threshold, dither-preservation strength,
sharpen amount, temporal blend weight (FR5).
**Skeleton built 2026-09-17** (`shaders/shaders_slang/argus/`): passthrough pass with all four FR5
parameters declared, passing both T-002's compile gate and a T-003 render/golden check.
- [x] All FR5 parameters declared with sane defaults and documented ranges
- [ ] Parameters surface and adjust live in RetroArch's shader menu — needs an actual RetroArch
      install to verify; not checkable from this environment
- [x] Compiles clean on all backends via T-002

### T-040 — Legacy `.glslp`/`.glsl` preset pack (added 2026-09-17)
**Track A · L · depends on T-013 (skeleton), tracks T-017/T-018/T-019/T-020 as each lands · new scope**
Ship a second, independently-formatted preset pack for RetroArch's older GLSL shader driver
(`.glslp` preset + single-file `.glsl` using `#if defined(VERTEX)`/`#elif defined(FRAGMENT)`
conditional compilation, `COMPAT_*` portability macros, implicit non-Vulkan-semantics uniform
bindings) alongside the primary `.slangp`/`.slang` pack, for RetroArch installs and non-RetroArch
frontends that predate or don't support the slang pipeline. This is **not** a byproduct of T-002's
SPIR-V/spirv-cross cross-compile — that pipeline's GL/GLES output targets the format the slang driver
consumes, which is structurally different from the legacy driver's expected file layout and uniform
conventions, even though the underlying per-pixel math can be shared conceptually between the two.
Confirmed against real examples in `libretro/glsl-shaders` (`stock.glsl`, `crt-pi.glsl`): the legacy
format's `#pragma parameter` syntax is identical to slang's, so FR5 parameter declarations translate
directly; only the file structure, stage-selection mechanism, and uniform/varying naming differ.
- [x] Root `.glslp` skeleton + `#pragma parameter` declarations mirroring T-013, using the legacy
      single-file `#if defined(VERTEX)`/`#elif defined(FRAGMENT)` structure and `COMPAT_*` macros
      (`shaders/shaders_glsl/argus/`, built 2026-09-17)
- [x] Compile gate extended to validate the legacy format (`tools/compile_gate/compile_check_legacy.py`,
      2026-09-17) — checks GLES 300, desktop GLSL 150/120, and (structurally, via the file's own
      `#if __VERSION__ >= 130` COMPAT_* branch) GLES 100, for both stages. **Caught a real bug** while
      building this: the shared `TEX0` varying was declared before any GLSL ES float precision default
      existed, which glslangValidator rejects outright in the fragment stage — fixed by moving the
      `precision mediump float` default before the shared declaration instead of leaving it fragment-
      branch-local (see the file's header comment for detail).
- [ ] Each tier's algorithm ported to legacy syntax as its slang counterpart lands (T-020 mobile-lite
      first), not written from scratch after the slang pack is finished
- [ ] Golden-image parity confirmed between the slang and legacy outputs within tolerance (T-003)
- [ ] Documented: which frontends/RetroArch versions require the legacy pack vs. the slang pack,
      and any feature the legacy driver cannot express (e.g., `OriginalHistory#` semantics for FR4 —
      confirm the legacy driver's history/feedback support before T-025 lands, since the two drivers'
      history models may not be equivalent)

### T-014 — Generate and bake the 3×3 topology LUT
**Track A · M · depends on T-001, T-004**
Build the 256-entry LUT mapping 3×3 binary edge topology to edge geometry (§6a.3).
- [x] All 256 entries generated by a committed, reproducible script (`tools/lut/generate_lut.py`)
- [x] Baked as a texture with documented format and no runtime dependency on the generator (`tools/lut/topology_lut.png` + `.bin`, RGBA8, format documented in the generator's docstring)
- [x] Sampling is divergence-free — no conditional branching on the lookup (direct `texelFetch`, documented; not yet wired into an actual shader pass since T-016 doesn't exist yet)
- [x] Symmetry/rotation invariants verified by unit test (`tools/lut/lut_test.py`, 7/7 passing)

### T-015 — Wide-kernel scalar statistics
**Track A · M · depends on T-004**
Implement local variance, checkerboard autocorrelation, stroke-width estimate, and unique-color
count over the 5×5 kernel in ALU — no table, no branching (§6a.3).
**Built 2026-09-17**: `tools/classifier_gpu/classify_debug.slang` (+ `reference.py`,
`verify_gpu.py`, `report.md`). Found and fixed two real numerical bugs along the way that T-004's
CPU-only spike couldn't have surfaced: the checkerboard-autocorrelation ratio is a 0/0-like
indeterminate form on flat windows that CPU float arithmetic happens to cancel exactly but a
GPU's different summation order doesn't (was producing false dither-positive noise on 77% of
pixels in one test image before a branchless signal-floor guard fixed it), and the unique-color
proxy needed 32 luma bins, not the 8 first tried, to resolve this corpus's own near-black
glyph-outline/background pair. See `report.md`'s six findings for the full detail.
- [x] Each statistic matches the T-004 offline reference within tolerance — variance/checkerboard/
      popcount verified to match; stroke-width's raw value is checked informationally rather than
      gated, because it diverges near flat/background windows (a `>=` tie) without ever changing
      the final classification — see `report.md` Finding 5.
- [x] ALU op count per pixel measured and recorded — `report.md`'s cost table, ~500 ops/pixel
      (estimated from source, not hardware-profiled — no profiler available in this environment)
- [ ] mediump-safe: no precision-induced misclassification versus highp reference — **partially
      closed.** The variance accumulator can overflow real fp16 mediump (sums up to ~1.6M vs.
      fp16's ~65504 max) and was declared `highp` rather than ship that unverified; the other three
      statistics are small enough in magnitude to be mediump-safe by construction but weren't
      empirically re-tested at mediump, since this software rasterizer likely executes mediump as
      fp32 internally and so can't actually exercise the failure mode either way. Needs real mobile
      hardware or a precision-accurate mediump emulator to close fully.

### T-016 — FR2 four-class region classifier
**Track A · L · depends on T-014, T-015 · critical path**
Combine LUT topology and scalar statistics into per-region classification: hard-edge/flat, dither,
AA'd gradient, thin monochrome stroke (FR2).
**Built 2026-09-17** alongside T-015, same files — `classify_debug.slang`'s DEBUG_MODE=1 output.
This is the classification decision logic (thresholds on T-015's four statistics) verified
end-to-end through the actual GLES render path against the T-004 corpus; it does **not** yet
consume T-014's baked LUT topology (that fusion, and folding this out of its current
debug-output-mode shader into a shipped pass, is T-020's job, combined with T-017/T-018/T-019's
reconstruction logic) — see `report.md`'s "What's still open" for the exact scope boundary.
- [x] Classifies all four classes at the T-004 accuracy threshold — dither-vs-gradient separation
      0.906, identical to T-004's own result; final-label agreement against the CPU reference
      checked directly (not just the separation score) at <1.3% mismatch across the corpus, with
      one documented, understood exception (see below)
- [x] Operates per-region within one shader — no genre-selected shader variants (FR2) — single
      shader, all four classes computed unconditionally per pixel
- [x] Mixed-content frames (art + text overlay simultaneously) classify correctly — verified
      against the corpus's checkerboard/dither/text categories together, not just isolated per-class
      test images
- [x] No divergent branching in the hot path — the classification logic itself uses only
      arithmetic selects (`?:` on scalars, no early-exit or texture-dependent branches); DEBUG_MODE's
      own branch is a uniform (not per-pixel data-dependent) selector between two debug output
      encodings and won't exist in the fused shipped pass this promotes into

One corpus category (`text_negative/architecture_*.png`) sits close enough to the
`CHECKERBOARD_HI` threshold that independent floating-point implementations can legitimately land
on either side of it — not a bug, documented in `report.md`'s Finding 6, and excluded from the
general tolerance check specifically so it can't mask a real regression by loosening a shared bar.

### T-017 — Text/glyph protection path (class d)
**Track A · M · depends on T-016, T-009, T-010**
Route class (d) to minimal-interpolation/nearest-preserving reconstruction rather than diagonal
reconstruction (FR2).
**Built 2026-09-17**: `tools/text_protect/` (`text_debug.slang`, `text_reference.py`, `verify_gpu.py`,
`report.md`). Same debug-shader-verified-against-CPU-reference pattern as T-015/T-016/T-019. The
reconstruction rule itself is verified and demonstrably beneficial (see first box); the
false-positive box surfaced a real, pre-existing classifier-separability limit that this ticket's
reconstruction rule cannot itself close — tracked as new scope in **T-041** rather than asserted as
passing. See `report.md` for the full evidence (a real per-statistic separability check across
`text_positive`/`text_negative`, not a guess).
- [x] Legibility on T-009 scores at or above nearest-neighbour on the rubric — measured 0.651 mean
      (nearest-neighbour baseline = 1.000 by definition); checked against a real comparison baseline
      (no class-d special case at all: 0.002 mean) to make this a substantive claim, not a tautology
      — see `report.md`
- [ ] False-positive rate on T-010 within the threshold agreed in T-010 — **no threshold can honestly
      be agreed against the current statistic set.** Measured 80.8% (unchanged from T-004/T-010's own
      baseline), and `report.md` shows directly that none of T-015's four wide-kernel statistics
      separate `text_negative` from `text_positive` on this corpus — they were deliberately built to
      share the same signature. This is a real, evidenced limitation of the classifier this ticket
      depends on (T-016), not a gap in this ticket's own reconstruction rule; see T-041 (new ticket,
      below) for where the actual fix belongs.
- [ ] Both sets gate this ticket together — positive-only is not sufficient to close; per the above,
      this box stays open pending T-041

### T-041 — Class (d) separability beyond the 5x5 wide-kernel statistic set (added 2026-09-17)
**Track A · M · depends on T-016, T-017 · new scope**
T-017's report (`tools/text_protect/report.md`, Finding 1) measured, directly and per-statistic, that
none of T-015's four wide-kernel statistics (variance, checkerboard-autocorrelation, luma-bin
popcount, stroke-width) can separate real glyph strokes from T-010's fur/hair, architectural-grid,
and weapon-outline content — they were deliberately built to share the same thin-high-contrast-stroke
signature, and a measured 80.8% false-positive rate confirms the statistics genuinely can't tell them
apart, not that thresholds are merely mistuned. This is the risk T-004's spike report and T-010 both
flagged in advance and deferred to this point; T-017 is where it stopped being deferrable.
- [ ] Candidate approach evaluated and a decision recorded: a wider secondary kernel for
      density/periodicity (architecture's grid spacing, fur's local stroke density) — noting the
      tension with §6a.3's ALU-budget-driven small-kernel decision — vs. fusing T-014's LUT topology
      (built, not yet consumed by T-016) for connectivity/grid-alignment cues, vs. formally accepting
      the current false-positive rate as a permanent tradeoff (T-017's report already establishes that
      misrouting to nearest-preserving reconstruction is a safe, if suboptimal, fallback — not a
      correctness bug)
- [ ] Whichever approach is chosen, re-measured against the same `text_positive`/`text_negative`
      per-category table `tools/text_protect/report.md` already established, so the before/after is
      directly comparable
- [ ] T-017's backlog entry updated to reflect the resolution (checked or explicitly accepted-as-is)

### T-018 — Edge reconstruction from LUT topology
**Track A · L · depends on T-014, T-016, T-001**
Reconstruct edges/curves for classes (a) and (c) using LUT-supplied geometry.
**Built 2026-09-17**: `tools/edge_reconstruct/` (`edge_debug.slang`, `edge_reference.py`,
`regenerate_lut_glsl.py`, `verify_gpu.py`, `report.md`). Same debug-shader-verified-through-the-
real-render-harness pattern as T-015/T-016/T-019/T-017. Building this surfaced a real, reproducible
Mesa/llvmpipe compiler bug (dynamically-indexed `texelFetch` on a second sampler corrupts unrelated
shader state) — worked around for this pre-fusion debug shader by embedding T-014's LUT as a
generated GLSL constant array instead of sampling its texture; see `report.md` Finding 1 for the full
isolation and why T-020's real shipped pass should still use T-014's texture as designed, re-verified
against a real GPU driver. Also found that scaling the reconstruction blend by LUT confidence
(plausible-sounding, tried first) measurably *hurt* sub-pixel accuracy — removed, see Finding 2.
- [x] No regression versus nearest-neighbour on flat-color sprite art — measured 0px difference on
      `checkerboard_transparency`'s flat background region at 3x scale (`report.md`)
- [x] Sub-pixel edge placement preserved — verified against integer-scale reference — mean sub-pixel
      edge-position error against the diagonal sweep's own analytic ground truth: 1.051px vs.
      nearest-neighbour's 1.537px (lower is better) at 4x scale (`report.md`)
- [ ] Beats SABR and Omniscale on the diagonal sweep (T-008) at matched output resolution —
      **Omniscale: measured honestly across every scale RetroArch would realistically run this tier at
      (2x-6x), not just one — wins 1 of 5 tested scales, loses by a similar margin at the other four
      (`report.md` Finding 2's full table). Not a threshold this ticket can claim passing.** SABR: not
      run at all — this project's own T-011 backlog entry already treats even *running* SABR's
      unmodified code for comparison as gated on a human licensing-scope decision, not a new call this
      ticket makes unilaterally (see `reference_shaders/NOTICE.md`).

### T-019 — Dither preservation rule
**Track A · M · depends on T-016**
Reconstruction rule for class (b) that preserves intentional dithering rather than smoothing it away
(Goal 2, FR9 system axis).
**Built 2026-09-17**: `tools/dither_reconstruct/` (`dither_debug.slang`, `dither_reference.py`,
`generate_soft_dither.py`, `verify_gpu.py`, `report.md`). Debug/test shader verified against a CPU
reference through T-003's render harness, same pattern as T-015/T-016 — not yet fused into the
shipped mobile-lite pass (T-020's job) and only defines class (b)'s own rule; non-dither pixels
are an unfiltered placeholder here, not classes (a)/(c)/(d)'s real reconstruction.
- [x] Checkerboard-transparency block (T-008) survives without being blurred to flat color —
      mean |rendered-source| over the dither region = 0.000 at default strength (`report.md`)
- [x] Genesis-style manual dithering visibly preserved — the case §5 FR9 flags as most at risk —
      same 0.000 deviation result on `dither_ramp`'s top half
- [x] Behavior differs measurably between NES-style hard dither and SNES-style blending — required
      generating new test content (`corpus/synthetic/dither_soft/`, see `report.md` Finding 1); no
      existing corpus sample isolated close-color ("soft") ordered dithering. Measured 2.04x more
      blending on the soft case than the hard case at a shared partial strength setting.

### T-020 — Fuse into single-pass mobile-lite shader
**Track A · L · depends on T-017, T-018, T-019, T-005 · critical path**
Fuse classification and reconstruction into one fragment shader: fixed unrolled neighborhood, no
intermediate render targets, mediump, `textureGather` where available (FR3, §6a).
**Built 2026-09-17** (`shaders/shaders_slang/argus/shaders/mobile-lite.slang`, driven by
`argus-mobile-lite.slangp`) — see `tools/fusion/report.md` for the full write-up, including a real
gap this ticket found and fixed in the render harness's own regression goldens (Finding 1: `scale0 =
1.0`, inherited from T-013's passthrough skeleton, made T-018's edge reconstruction a mathematical
no-op, so the previously-committed goldens were silently testing nothing of this ticket's logic —
fixed to `scale0 = 4.0`, all 60 goldens regenerated and visually spot-checked before committing).
- [x] Exactly 1 pass, 1 output-resolution pass, zero intermediate RTs — verified directly from
      `argus-mobile-lite.slangp` (`shaders = 1`, `scale_type0 = viewport`)
- [x] Base coord + texel size as varyings only (≤2 vec4) — offsets computed in FS (§6a.6, B3) —
      verified via compiled GLES reflection: exactly one `vec2` varying (`vTexCoord`) crosses the
      vertex/fragment boundary; no texel-size varying at all (texel size read from the `SourceSize`
      uniform instead); every neighbor tap is `texelFetch(base + offset)` computed in the fragment
      shader
- [ ] Varying count verified ≤16 vec4 on Adreno 6xx — no physical device available in this
      environment (same limitation as T-006/T-021/T-018); the compiled reflection shows 1 varying,
      trivially within any GLES 3.1 floor, but that's not the same as a device-verified claim
- [ ] `textureGather` used where available, with the T-005 fallback path if required — not attempted;
      every tap is an individual `texelFetch`, matching what each contributing debug shader already
      verified. Real, tracked perf optimization (`tools/fusion/report.md`), deliberately out of this
      ticket's scope to avoid re-verifying the fetch pattern from scratch without a bandwidth/frame-
      time measurement (T-021/T-022) to check it against
- [ ] `mediump` precision (per this ticket's own prose and FR8/§5) — kept `highp` throughout, same as
      every contributing debug shader. This was flagged as this ticket's job by T-015's own report
      (`tools/classifier_gpu/report.md` Finding 3: the variance accumulator can overflow real `fp16`
      `mediump` on hardware this environment's `mediump`-as-`fp32` software path can't reproduce) —
      not attempted here; downgrading precision without a real device to catch an overflow regression
      would be an unverified change, which this project's discipline doesn't ship

### T-021 — Bandwidth (B/px) instrumentation
**Track B · M · depends on T-006**
Wire the T-006 methodology into a repeatable measurement reported per tier alongside frame time
(§6, O2).
- [ ] Reports measured B/px, RT format sizes, and fetch count per tier
- [ ] Runs on both reference handheld and desktop
- [ ] Output is machine-readable so CI can assert against tier ceilings

### T-022 — Phase 1 exit validation
**Track A/B/C · M · depends on T-020, T-021, T-003, T-011**
Gate Phase 1 against §10 exit criteria.
- [ ] ≤ 8 B/px measured on reference handheld
- [ ] 60fps at 1080p on reference handheld
- [ ] Beats nearest-neighbour and SABR on the perceptual set
- [ ] Text legibility no worse than nearest-neighbour
- [ ] False-positive rate on T-010 within threshold
- [ ] Goldens committed for all tiers/backends

---

## Phase 2 — Mobile/mid tier, temporal, preset matrix

### T-023 — Native-res classification render target (pass 1)
**Track A · M · depends on T-016 · critical path**
Pass 1 runs at native resolution and emits a compact 8-bit classification + edge-parameter buffer —
**not** a reconstructed image (FR3, O1).
- [ ] RT is 8-bit, native resolution, alpha dropped unless demonstrably needed
- [ ] Packs region class, dominant edge direction, and blend weight
- [ ] Measured cost ≤0.5 B/px at 1080p output
- [ ] Round-trips without precision loss that changes classification

### T-024 — Pass 2 expansion from classification buffer
**Track A · M · depends on T-023**
Pass 2 consumes the classification buffer and performs the actual upscale, sharpen, and temporal
blend (FR3).
- [ ] Output matches the fused mobile-lite result within tolerance on non-temporal content
- [ ] Exactly 1 output-resolution pass
- [ ] Sub-pixel edge placement preserved through the buffer hand-off

### T-025 — `OriginalHistory1` temporal stability signal
**Track A · L · depends on T-024 · critical path**
Derive a per-pixel stability signal from the previous frame's core input at native resolution, used
to modulate reconstruction strength. **No output-to-output feedback path** (FR4, B4).
- [ ] Uses `OriginalHistory1`, not `PassFeedback` — verified in the compiled reflection
- [ ] History read costs ≤0.5 B/px at 1080p output
- [ ] Measurable shimmer reduction on the parallax set
- [ ] No ghosting regression on fast-action content (small fast-moving sprites)
- [ ] Toggleable per FR4; disabling it removes the cost entirely

### T-026 — Temporal correctness edge cases
**Track A/C · M · depends on T-025**
Cover the hazards the spec and RetroArch features create (§8, NFR, P8).
- [ ] Cold start: N<0 history reads transparent black — degrades to non-temporal, does not blend to black
- [ ] Reset and save-state restore behave as cold start
- [ ] **Rewind:** reversed frame order does not invert or corrupt the motion signal
- [ ] Run-ahead frame re-simulation produces no visual artifact
- [ ] Mid-session resolution change (FR1) does not read stale-geometry history
- [ ] Measured added visual lag <1 frame (NFR)

### T-027 — System and genre profile tables
**Track A/C · M**
Two independent low-cardinality parameter tables: palette/dither per system (NES/SMS, SNES,
Genesis, GB/GBC, GBA) and motion per genre (fast-action, scrolling-heavy, text/low-motion,
static/turn-based) (FR9).
- [ ] Both tables in a structured format (YAML/JSON), one file per axis
- [ ] Every parameter value carries a one-line rationale tied to art or motion convention
- [ ] Axes are genuinely independent — no genre value referencing a system value

### T-028 — Preset matrix generator
**Track B · M · depends on T-027**
Generate the flat (system × genre) cross-product. RetroArch does not support references-to-
references, so the axes must be merged at build time — one `#reference` to the root preset plus
merged parameters per file (FR9, B1).
- [ ] Emits ~20 flat `.slangp` files, each with exactly one `#reference`
- [ ] Regenerates reproducibly — byte-identical output from unchanged tables
- [ ] CI fails if generated presets are stale relative to the tables
- [ ] Every generated preset loads in RetroArch without error
- [ ] No hand-editing: generated files marked as such in a header comment

### T-029 — Pixel aspect ratio correctness
**Track A · S · depends on T-024**
Respect each console's native pixel aspect rather than assuming square pixels (FR7).
- [ ] Correct PAR per system in each generated preset
- [ ] Non-square-pixel content renders without horizontal/vertical distortion
- [ ] Reconstruction geometry accounts for PAR — diagonals stay at the intended angle

### T-030 — Dynamic geometry handling
**Track A/C · M · depends on T-024**
Handle mid-session `base_width`/`base_height` changes: SNES Mode 7, GBA affine transforms (FR1).
- [ ] No artifact or crash on mid-session geometry change
- [ ] Mode 7 and GBA affine titles render correctly through a full transition
- [ ] Classification adapts to the new geometry within one frame
- [ ] Regression test added to the golden-image harness

### T-031 — Per-backend runtime verification
**Track B · M · depends on T-025, T-002**
Backends already compile (T-002); verify *runtime* behavior — output equivalence, not just build
success (P1).
- [ ] Golden-image parity across GL, Vulkan, D3D11/12, Metal within tolerance
- [ ] Any backend-specific divergence documented with root cause
- [ ] Zero backend-specific forks in the shader source (NFR)

### T-032 — Phase 2 exit validation
**Track A/B/C · M · depends on T-026, T-028, T-030, T-031**
Gate Phase 2 against §10 exit criteria.
- [ ] ≤ 10 B/px measured
- [ ] All T-026 temporal correctness cases pass
- [ ] Preset matrix regenerates reproducibly
- [ ] Shimmer reduction measured on parallax set, no ghosting regression on fast-action
- [ ] Backend parity confirmed

---

## Phase 3 — Desktop tier & polish

### T-033 — Desktop tier smoothing/diffusion pass
**Track A · L · depends on T-024 · critical path**
Add the higher-quality tier: up to 4 total passes, ≤2 at output resolution (FR3).
- [ ] ≤2 output-resolution passes — total pass count is secondary (O1)
- [ ] ≤ 32 B/px measured
- [ ] Contour quality measurably beats the mobile/mid tier on the diagonal sweep
- [ ] Beats ScaleFX on perceptual comparison at equal or better frame time

### T-034 — Compose-testing with bezel/CRT shaders
**Track A/C · M · depends on T-033**
Confirm this shader sits earlier in a combined chain without conflicting render-target assumptions
(§7).
- [ ] Composes with Mega Bezel without RT conflicts
- [ ] Composes with CRT-Royale without RT conflicts
- [ ] Combined-chain frame time recorded per tier
- [ ] Any ordering constraint documented for users

### T-035 — Community beta
**Track C · L · depends on T-033**
Blind preference survey with retro-gaming community testers across all tiers (§8).
- [ ] Blind A/B run via T-012 against xBRZ, ScaleFX, SABR, and nearest-neighbour
- [ ] ≥50 responses across forums.libretro.com and r/emulation
- [ ] Results broken out by tier and by content category
- [ ] Feedback triaged into fix-now / backlog / won't-fix

### T-036 — Phase 3 exit validation
**Track A/B/C · M · depends on T-033, T-034, T-035**
Gate Phase 3 against §10 exit criteria.
- [ ] ≤ 32 B/px measured; 60fps at 4K on desktop reference GPU
- [ ] Composes with ≥1 bezel and ≥1 CRT shader
- [ ] Blind survey shows preference over ScaleFX at equal or better frame time

---

## Phase 4 — Release

### T-037 — Per-tier documentation and device guidance
**Track C · M · depends on T-036**
Document which devices should use which preset — the tier system fails if users pick wrong (FR3).
- [ ] Each tier documented with target hardware and measured B/px
- [ ] Explicit guidance: mobile tiers are target platforms, not fallbacks (FR3)
- [ ] All FR5 parameters documented with effect and recommended ranges
- [ ] Install instructions for `shaders/shaders_slang/`

### T-038 — librashader parity verification
**Track B · M · depends on T-031**
Confirm the pack behaves identically under librashader, the Rust slang reimplementation used by
non-RetroArch frontends (§7).
- [ ] Golden-image parity between RetroArch and librashader within tolerance
- [ ] All generated presets load under librashader
- [ ] Any divergence documented and reported upstream

### T-039 — Upstream submission
**Track C · M · depends on T-037, T-038**
Submit to the libretro slang-shaders community repo (§10 Phase 4).
- [ ] Repo layout matches slang-shaders conventions
- [ ] Licensing headers consistent with the T-001 determination
- [ ] PR opened with per-tier guidance and comparison results
