# Backlog

Rewritten 2026-09-20 for the v0.3 pivot (`docs/requirements.md`). The full ticket-by-ticket history
of the v0.2 build (41 tickets, T-001 through T-047) is preserved in git history and is not
reproduced here — this file tracks only what's actually actionable now: infra that survives the
pivot unchanged, work that's retired because it served the old goal, and what's next.

## Reusable — done, unaffected by the pivot

Evaluation and build infrastructure doesn't encode a stance on "preserve blocky art" vs. "reconstruct
smooth art" — it just measures against ground truth, so all of it carries forward.

| What | Where | Notes |
|---|---|---|
| Cross-backend compile gate (GL/Vulkan/D3D/Metal, slang + legacy GLSL) | `tools/compile_gate/` | Gates every commit in CI |
| Headless golden-image regression harness | `tools/render_harness/` | Deterministic PNG diff per (content, preset, backend) |
| Multi-pass filter-chain sequencer | `tools/render_harness/render_multipass.py` | Runs real multi-pass third-party shaders (ScaleFX, xBRZ), not just single-pass |
| Ground-truth IoU scoring | `tools/eval_metric/` | Scores against an 8x-supersampled reference; includes real RPG dialogue/letterform content |
| **Gold-standard V/O regime eval** | `tools/gold_eval/` | The primary quality gate going forward — see `docs/requirements.md` §4/§7 |
| Comparison harness vs. real baselines | `tools/comparison/` | Runs nearest-neighbour, Omniscale, SABR, ScaleFX, xBRZ through the same harness |
| Perceptual A/B viewer | `tools/ab_compare/` | Spot-check tool, not the primary gate |
| Synthetic test corpus generators | `tools/patterns/`, `corpus/synthetic/` | Dither ramps, diagonal sweeps, glyph sheets, checkerboard blocks — reusable regardless of goal |
| Licensing posture for reference shaders | `docs/licensing.md` | xBRZ/SABR/HQx clean-room only (GPL); ScaleFX/Omniscale MIT, may derive |
| GLES floor decision | `docs/gles-floor.md` | Gather-only, no GLES 3.0 fallback, for the stated ARM handheld class |
| RetroArch install/A-B testing steps | `docs/retroarch-testing.md` | How to load and compare presets in a real install |
| `.slangp`/`.slang` and `.glslp`/`.glsl` preset skeletons, compiling clean on all backends | `shaders/shaders_slang/argus/`, `shaders/shaders_glsl/argus/` | Structure is reusable; the shipped reconstruction logic inside is not (see below) |

## Retired — served the old (now-reversed) goal

These aren't bugs to fix; they implement a goal `docs/requirements.md` v0.3 explicitly reverses.
Kept in git history for reference, not deleted, not on the active path.

| What | Where | Why retired |
|---|---|---|
| Dither-vs-AA-gradient classifier feasibility spike | `tools/classifier_spike/` | Dithering is no longer a protected class — nothing to separate it from |
| Four-class region classifier (hard-edge / dither / AA-gradient / text-glyph) | `tools/classifier_gpu/` | Built to route content to different treatment; new goal treats all content uniformly (FR2) |
| Dither-preservation reconstruction rule | `tools/dither_reconstruct/` | Directly contradicts the new goal — dithering should now be smoothed like any gradient |
| Text-to-nearest-neighbour "protection" rule | `tools/text_protect/` | Directly contradicts the new goal — text now gets the same reconstruction pipeline, judged on fidelity (FR3), not exempted from it |
| Text-negative false-positive test set | `corpus/synthetic/text_negative/` | Existed to gate the text-protection classifier above; no classifier to gate |
| Dual-axis system/genre tuning-profile design | (was v0.2 requirements §5 FR9) | Tuned dither-preservation strength per console; no longer applicable |
| Shipped `mobile-lite.slang` prototype | `shaders/shaders_slang/argus/shaders/mobile-lite.slang` | Fuses all of the above; scores worst-of-field on vector-regime content (`tools/gold_eval/report.md`) and has a real, evidenced GPU register-spilling anti-pattern found via real RetroArch testing |
| LUT-topology edge reconstruction (as tuned) | `tools/edge_reconstruct/` | The general technique (3×3 topology LUT → reconstruction rule) is still sound and worth keeping as a *reference implementation to improve on* — but its tuned output is what scored 80.5%/82.9% in §4, below xBRZ/SABR/ScaleFX, so it's a starting point, not a keeper as-is |

## Archived tickets

**T-001 through T-047 are archived.** They were the v0.1/v0.2 cycle and are closed as a set — what
survives is captured in the two tables above, and the full per-ticket text lives in git history
(`git log -- docs/backlog.md`). New tickets use the `F-` (fidelity) and `P-` (performance) prefixes
below so there's no ambiguity about which cycle a ticket ID belongs to.

---

# Next cycle — queued

Two tracks, worked in parallel; **F-1 gates the whole fidelity track and should be built first.**
The evidence base for this plan is the code-level diagnosis in `docs/backlog-status.md` (three
findings, each cited by line number in the retired shader) — the tickets below are written against
those findings, not against guesses.

The guiding idea, stated once: **reconstruct a local implicit contour per source pixel and rasterize
it with analytic coverage.** That is what a vector renderer actually does, and it's the direct
expression of `docs/requirements.md`'s goal. It also happens to be the cheap architecture (see the
P track), because the contour is a property of the *source* texel and only its rasterization varies
per output pixel.

## Scoring gates used below

From `tools/gold_eval/report.md`, vector regime (V-corner / O-ring), which is the primary metric:

| | nearest-neighbour | retired prototype | Omniscale | ScaleFX | SABR | **xBRZ (the bar)** |
|---|---|---|---|---|---|---|
| vector | 81.0 / 82.3 | 80.5 / 82.9 | 81.8 / 85.4 | 88.9 / 87.8 | 90.1 / 91.3 | **93.4 / 95.2** |
| 8bit | 100 (tautological) | 93.6 / 93.0 | 87.8 / 84.8 | 81.7 / 80.1 | 87.8 / 84.7 | 87.6 / 84.7 |

- **Primary gate:** vector regime ≥ **93.4 / 95.2** (match xBRZ).
- **Interim gate:** vector regime ≥ **88.9 / 87.8** (clear ScaleFX) — proves the model works at all.
- **Regression guard:** 8bit regime ≥ **87.6 / 84.7** (xBRZ's own 8bit score). Deliberately *not* the
  retired prototype's 93.6/93.0 — that number was produced by the nearest-neighbour-preserving path
  this project retired, and chasing it would re-import the reversed goal. The guard only says: don't
  be worse than the competition at leaving genuinely blocky art alone.

---

## Track F — visual fidelity

### F-1 — CPU reference implementation of the reconstruction model *(do this first)*
**Goal.** A numpy implementation of the candidate reconstruction, scored directly by
`tools/gold_eval`, with no shader compile or GPU in the loop.
**Why.** The algorithm is the risk, not the shader. Today every candidate costs a
glslangValidator→SPIR-V→spirv-cross round trip plus a fresh EGL context per render (see P-4), so
iteration is minutes; in numpy it's seconds, and driver/rasterizer bugs are out of the loop
entirely. Every previous algorithmic conclusion in this project was reached through the slow path.
**Acceptance.** Reproduces the retired prototype's published vector/8bit scores from
`tools/gold_eval/report.md` within ±0.5pp when fed the same logic (proving the reference path is
faithful), then serves as the iteration surface for F-2/F-3. Runs the full four-shape sweep in
< 5 seconds.

### F-2 — Continuous-orientation contour estimation (replaces compass snapping)
**Goal.** Per source pixel, estimate a local edge as a continuous orientation + signed offset (an
implicit line), and evaluate per output pixel as analytic coverage over one output-texel width,
blending the two colours the contour separates.
**Why.** Diagnosis finding 2: the retired model rounds its edge normal to one of 8 compass
directions and lerps between two texels, which cannot represent a shallow slope or a curve at all.
This is the fidelity ceiling, and it's structural — T-046 already showed tuning doesn't move it.
**Acceptance.** Vector-regime score clears the interim gate (≥ 88.9 / 87.8) in the F-1 reference.
8bit regime stays ≥ the regression guard *without* a special-case path — an axis-aligned estimated
contour should reproduce blocky output naturally; if it doesn't, that's the finding to report.
**Depends on:** F-1.

### F-3 — Corner/wedge model for sharp vertices and thin strokes
**Goal.** Where two edges meet, represent the local geometry as *two* half-planes (a wedge) rather
than one line: coverage becomes the intersection (or union) of two signed distances.
**Why.** A single-line model necessarily rounds corners — that is Omniscale's documented failure
(81.8/85.4, barely above nearest-neighbour) and the visible cross-hatch artifact the gold eval found
at the retired prototype's V vertex. It's also what erodes 1-2px strokes, which is most of what a
bitmap font *is*. A wedge reproduces a sharp vertex exactly and holds a thin stroke at its true
width, so it's the single mechanism most likely to beat xBRZ specifically on text.
**Acceptance.** Vector-regime score clears the **primary gate** (≥ 93.4 / 95.2) on both shapes;
visual audit of the V vertex shows no artifact at the corner; 8bit guard holds.
**Depends on:** F-2.

### F-4 — Perceptual colour distance for region membership
**Goal.** Decide "same region or not" with a weighted YCbCr-style distance instead of the retired
luma-threshold and 32-bin luma-popcount proxies.
**Why.** Every contour estimate in F-2/F-3 is downstream of that decision, and a luma-only test
merges colours that differ strongly in chroma (a real case in 16-bit palettes). Published
descriptions of xBRZ attribute real weight to its perceptual distance metric.
**Acceptance.** Measured as a delta on F-3's scores — kept only if it helps, reported honestly as a
null result if it doesn't (see T-046's precedent).
**Depends on:** F-2.

### F-5 — Text/glyph fidelity gate (FR3)
**Goal.** Score real bitmap-font content across at least three font styles — thin sans-serif,
outlined/drop-shadow, blocky — not just the two RPG scenes that already exist.
**Why.** FR3 makes text a first-class pass/fail criterion rather than an assumed side effect, and
the existing RPG content is dominated by near-axis-aligned box borders that bypass the
reconstruction path almost entirely (T-046 experiment 1 demonstrated this directly). A gate that a
change can't fail isn't a gate.
**Acceptance.** Corpus extended with the two missing font styles; argus matches or beats xBRZ and
clearly beats Omniscale on every style; results committed as a report alongside the existing
`tools/eval_metric/rpg_text_report.md`.
**Depends on:** F-3.

### F-6 — GPU port of the validated model
**Goal.** Port the F-3/F-4 reference into the two-pass shader architecture from P-1.
**Why.** Porting only after the model clears its gates keeps algorithm bugs and shader bugs from
being diagnosed at the same time — the failure mode that cost this project a full cycle.
**Acceptance.** GPU output matches the F-1 reference within tolerance on the gold-eval shapes;
compile gate green on all five backends; P-2's static cost report shows no register spill.
**Depends on:** F-3, P-1, P-2.

---

## Track P — performance and streamlining

### P-1 — Split into native-res analysis + output-res evaluation
**Goal.** Pass 1 runs at source resolution and emits a compact per-texel contour descriptor; pass 2
runs at output resolution and does only the coverage evaluation and colour blend.
**Why.** Diagnosis finding 1: the retired shader recomputes an identical 33-tap classification for
every output pixel inside a source texel — ~94% redundant at 4x, ~97% at 6x. Moving analysis to
native resolution removes that multiplier outright, and it's the same change that makes a *better*
(wider, more expensive) analysis affordable in F-2/F-3. The native-res render target it costs is
~0.2 B/px against the ~8 B/px an output-res pass costs.
**Acceptance.** Analysis cost scales with source resolution, not output resolution (demonstrable by
construction and by a fetch-count audit); pass 2 reads its descriptors in a single `textureGather`
where possible; re-derived B/px bound documented for 2x-6x, replacing
`tools/bandwidth_estimate/report.md`'s now-obsolete 15.1-40 B/px figure.

### P-2 — Static shader cost analysis in CI
**Goal.** Automated per-shader report: SPIR-V instruction count, temp/register pressure, dynamic
indexing sites, and spill indicators — failing the build on regression.
**Why.** This is the substitute for the blocked reference handheld, and it's what would have caught
the retired shader's spill hazard and its dynamically-indexed 256-entry constant array *before*
real-hardware testing did. Software rasterization models neither. Investigate whether Arm's Mali
Offline Compiler and/or the Adreno offline compiler are obtainable here (both give cycle and
register estimates with no device); fall back to SPIR-V/spirv-cross statistics if not.
**Acceptance.** Report generated in CI for every shipped pass; thresholds set from the current
shaders; regression fails the build. Honest note in the report about what static analysis can and
can't tell you without hardware.

### P-3 — Remove the known-bad preset from the shipped pack
**Goal.** Stop shipping `argus-mobile-lite.slangp` as a loadable preset — move it under an
`experimental/` path or remove it until the F track produces a replacement.
**Why.** It is currently measured as worse than doing nothing on the content most real games are made
of, and `docs/retroarch-testing.md` tells users how to load it. Shipping a preset we know
underperforms nearest-neighbour is a correctness problem, not a cosmetic one.
**Acceptance.** Pack contains no preset that fails the regression guard; `docs/retroarch-testing.md`
updated to match; CI's shader globs still cover whatever remains.

### P-4 — Make the dev loop fast
**Goal.** Cache shader compiles by source hash and reuse one EGL context across renders in
`tools/render_harness/render_pass.py`; pass output scale explicitly instead of reading `scale0` from
the preset.
**Why.** Today `render_pass()` creates a fresh `HeadlessContext` *and* re-runs the full
glslangValidator → spirv-cross toolchain (multiple subprocesses) on **every single render call**, so
an eval sweep pays that cost once per shape per candidate per regime. This is the CPU-side cost the
whole F track is gated behind. Separately, the shipped preset carries `scale0 = 4.0` purely because
the harness reads that field literally while RetroArch ignores it — test configuration doesn't belong
in a shipped artifact (see P-3).
**Acceptance.** Full `tools/gold_eval` sweep runtime cut by ≥ 5x; identical scores before and after
(this is a refactor, and must be proven to be one).

### P-5 — Reproducible environment
**Goal.** A dependency manifest and setup script, plus a SessionStart hook so a fresh checkout can
run the harness without archaeology.
**Why.** There is no `requirements.txt`, no `pyproject.toml`, and no setup script anywhere in the
repo — the Python and Mesa/EGL dependencies exist only implicitly inside
`.github/workflows/compile-gate.yml`. A fresh container in this very session couldn't run
`tools/gold_eval/run_eval.py` at all (`ModuleNotFoundError: numpy`), which is a silent tax on every
future session and every contributor.
**Acceptance.** `pip install -r requirements.txt` plus one documented system-package line is
sufficient to run the full harness from a clean checkout; CI installs from the same manifest rather
than a hand-maintained apt list; SessionStart hook wires it up automatically.

### P-6 — Real-hardware measurement protocol (still blocked, but write it now)
**Goal.** A written, step-by-step measurement protocol — which frame-time and bandwidth counters,
which content, which scales, what a pass looks like — ready to run.
**Why.** The reference handheld remains unavailable, but the protocol doesn't require one to author,
and having it ready converts "get a device" from a research project into a half-hour task. The
previous cycle discovered its performance problem from a user's subjective report, not a measurement.
**Acceptance.** Protocol committed; every number it asks for has a defined method and a pass
threshold; explicitly states which of P-2's static estimates it is meant to confirm or refute.

---

Still blocked on external resources, unchanged by the pivot: a physical ARM reference handheld
(P-6) and a real-game redistributable content corpus beyond what's synthetic/RPG-generated (F-5
partially mitigates this by broadening the font styles that can be generated synthetically).
