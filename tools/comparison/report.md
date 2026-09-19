# T-011 — comparison set against other reference shaders

Runs argus-mobile-lite (T-020's shipped pass) against the reference
shaders requirements.md §4 names, at matched output resolution, per
T-011's acceptance criteria: "Every corpus item rendered through all five
baselines at matched output resolution... nearest-neighbour included as
the honest control." Two of five are actually executed here; the other
two remaining gaps (real-game content, xBRZ/SABR/HQx execution) are
existing, already-tracked project blockers, not new ones — see "What's
still open."

Reproduce with:

```
python3 tools/comparison/generate_baselines.py     # writes tools/comparison/renders/{baseline}/...
```

Then load any two `tools/comparison/renders/<baseline>/` directories into
`tools/ab_compare/index.html` (T-012) for a visual, filename-matched A/B —
or diff them programmatically, as below.

## What's compared, and why only these two

| Baseline | License | Status |
|---|---|---|
| Nearest-neighbour | N/A (this project's own honest control) | **Run** |
| Omniscale | MIT (`docs/licensing.md`: "go") | **Run** |
| ScaleFX | MIT (`docs/licensing.md`: "go") | Vendored, **not run** — see below |
| xBRZ | GPLv3 (`docs/licensing.md`: "clean-room only") | Not vendored, **not run** — needs a licensing-scope call |
| SABR | GPLv2+ (`docs/licensing.md`: "clean-room only") | Not vendored, **not run** — needs a licensing-scope call |
| HQx | LGPL 2.1 (`docs/licensing.md`: "conditional, default no-go") | Not vendored, **not run** — needs a licensing-scope call |

**ScaleFX is vendored** (`reference_shaders/scalefx/`, unmodified, MIT,
cleared for execution) **but not rendered**: it's a 6-pass filter chain
with named cross-pass texture aliasing (pass 2 reads pass 0's output by
alias, pass 4 reads both `Source` and a separate reference-pass alias) and
float intermediate framebuffers. This project's render harness
(`render_pass.py`/`run_harness.py`) is explicitly single-pass only — no
multi-pass filter-chain sequencer exists yet (the same category of
infrastructure Phase 2's T-023/T-024 will need for this project's own
2-pass Mobile/mid tier). Building one just to run this comparison risked
shipping an unverified renderer and trusting its numbers over a real
concern; not attempted here. See `reference_shaders/NOTICE.md`.

**xBRZ/SABR/HQx are not vendored at all.** All three are copyleft with no
permissive subset covering direct execution, and T-011's own backlog entry
already treats even *running* their unmodified code for comparison
purposes as needing a human licensing-scope decision — not a call this
ticket makes unilaterally (same position T-018 already established for
SABR specifically). **Flagging this back to the project owner rather than
deciding it silently**, per this project's own documented practice for
exactly this kind of call.

## Method

Full synthetic corpus (`corpus/synthetic/`, 55 real content images,
`*_mask.png` reference masks excluded), rendered at `scale = 4.0` — matching
`argus-mobile-lite.slangp`'s corrected `scale0` (see `tools/fusion/report.md`
Finding 1) — through argus-mobile-lite (default parameters) and Omniscale,
plus a plain PIL nearest-neighbour upscale as the honest control. Omniscale
rendered through the same GLES cross-compile/render path as our own shader
(`render_pass.py`), not a separate implementation.

## Result — objective difference from nearest-neighbour, by content category

`MAE` = mean absolute per-channel difference from the nearest-neighbour
control (0 = pixel-identical to NN; **not** itself an accuracy or quality
score — see the note below the table).

| category | argus-mobile-lite MAE vs NN | omniscale MAE vs NN | argus % pixels changed vs NN |
|---|---:|---:|---:|
| checkerboard_transparency | 0.000 | 0.212 | 0.00% |
| diagonal_sweep | 0.236 | 0.311 | 0.24% |
| dither_ramp | 0.067 | 0.459 | 0.14% |
| dither_soft | 0.000 | 0.113 | 0.00% |
| **glyph_sheet** | **0.000** | **9.721** | **0.00%** |
| text_negative | 0.054 | 0.240 | 0.07% |
| text_positive | 1.213 | 1.728 | 1.42% |

**A higher or lower MAE here is not automatically "better" or "worse"** —
it only says how much a baseline diverges from plain nearest-neighbour, and
divergence is the intended behavior of every reconstruction algorithm
(including this project's own) on content that isn't flat. It's evidence
worth reading alongside the actual visual result and the one place this
project has real ground truth (below), not a substitute for either.

## The one place there's real ground truth: diagonal-edge sub-pixel accuracy

This transfers directly from T-018's own report rather than being
re-derived: `tools/fusion/verify_gpu.py` already proves the fused shader's
output for edge/gradient-classified pixels is bit-for-bit identical to
`edge_debug.slang`'s output (0-pixel difference, every sample tested,
including `diagonal_sweep/nes_256x240.png`) — the same content and pixels
T-018's sub-pixel-vs-analytic-ground-truth comparison against Omniscale
already measured. That result is unchanged by fusion and is not recomputed
here:

| scale | argus-mobile-lite MAE (px) | omniscale MAE (px) | result |
|---|---|---|---|
| 2x | 0.532 | 0.313 | loss |
| 3x | 1.016 | 0.922 | loss |
| 4x | 1.051 | 1.110 | **win** |
| 5x | 2.024 | 1.883 | loss |
| 6x | 2.468 | 2.057 | loss |

Wins 1 of 5 tested scales — see `tools/edge_reconstruct/report.md` Finding
2 for the full analysis (leading hypothesis: compass-direction-snapping
loses accuracy at shallow angles where Omniscale's continuous-direction
blend doesn't).

## Visual finding: glyph preservation vs. Omniscale

`glyph_sheet`'s 9.721-vs-0.000 MAE gap (the largest in the table) reflects
a real, visually obvious difference, not a measurement artifact. Cropping
`glyph_sheet/smw_256x224.png` (a repeated bitmap "A" glyph tile):

- **argus-mobile-lite**: pixel-identical to nearest-neighbour — sharp,
  blocky letterforms, corners intact.
- **omniscale**: visibly rounds and anti-aliases every glyph corner,
  softening the letterforms.

This is T-017's text/glyph protection rule (FR2 class (d)) doing exactly
what it's designed to do — Omniscale has no equivalent per-region
protection mechanism, so it applies the same smoothing rule to text that it
applies to everything else. This is the single clearest, most visually
legible win in this comparison set, and directly supports (without fully
closing — that needs T-022's actual perceptual-set run) the "text
legibility no worse than nearest-neighbour" bar T-022 will check.

## What's still open

- **ScaleFX execution** needs a multi-pass filter-chain sequencer this
  project doesn't have yet (see above) — the shader itself is vendored and
  ready whenever that infrastructure lands.
- **xBRZ/SABR/HQx execution** needs a licensing-scope decision from the
  project owner (accept copyleft obligations on specifically those
  comparison runs, or continue characterizing them from published
  documentation/screenshots instead, per T-011's own already-recommended
  fallback) — not decided here.
- **T-007's real-game corpus** is still needed for full T-011 coverage;
  this comparison set uses only the synthetic corpus, same limitation as
  every other tooling result in this project so far.
- This is a comparison set, not T-022's actual Phase 1 exit validation —
  no perceptual-set survey, bandwidth, or frame-time numbers are produced
  here.
