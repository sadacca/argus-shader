# Requirements Document: Vector-Faithful Upscaling Shader for 8/16-bit Console Art
**Status:** Draft v0.3 — pivot from v0.2
**Date:** 2026-09-20 (v0.2: 2026-08-30, v0.1: 2026-08-29)

> **v0.3 pivot note.** v0.1/v0.2 optimized for preserving the source's blocky pixel grid and
> deliberate dithering, with text specially routed to a nearest-neighbour "protection" path. Real
> RetroArch testing and this project's own gold-standard eval (`tools/gold_eval/report.md`) showed
> that goal was wrong: on content with a genuine smooth/curved source (most real game art), that
> approach tied or lost to doing nothing at all, while xBRZ/SABR/ScaleFX all cleared a real margin
> over nearest-neighbour. This revision replaces the goal. The evaluation harness built under v0.2
> (render harness, IoU/ground-truth scoring, gold V/O eval, comparison tooling) is unaffected and
> remains the validation mechanism — see §9 for the full account of what changed and why.

## 1. Purpose

8-bit and 16-bit console art implies shapes, curves, and letterforms beyond what its pixel grid can
express — the entire tradition of edge-directed upscaling (HQx, xBRZ, ScaleFX, SABR, Omniscale)
already treats the low-resolution source as a *sampling* of that intended art and reconstructs it.
This project makes the same assumption explicit: **the source is treated as a rasterized
approximation of continuous ("vector") artwork, and the shader's job is to recover that continuous
art as faithfully as it can** — not to keep the pixel grid visible. The differentiator against the
existing field is fidelity on **text and glyphs** specifically: a well-documented weak point of
these scalers (§4), and the content type players spend the most continuous time looking directly at
(dialogue boxes, menus, HUDs).

## 2. Goals

- Smooth, curve-faithful upscaling in the same family as xBRZ/Omniscale/ScaleFX/SABR — diagonal
  edges and curves reconstructed as continuous shapes, not left blocky.
- **Beat the existing field specifically on text/glyph fidelity.** Concretely: match or beat xBRZ's
  score and clearly beat Omniscale's on `tools/gold_eval`'s letterform-shaped hard cases (sharp
  corners, curved strokes), where Omniscale visibly rounds corners it shouldn't.
- Treat all image content uniformly under one reconstruction goal — no separate "protect this as
  blocky" path for text, dithering, or anything else.
- Ship as a standard `.slangp` preset (RetroArch / librashader compatible), no core modifications
  required.
- Reasonable performance on the ARM handheld class RetroArch commonly runs on (Retroid/Anbernic/
  Steam Deck), not desktop-only — but performance work follows a correct, honestly-measured
  algorithm, not the other way around; see §9 for why the previous performance work is being redone.

## 3. Non-Goals

- **Preserving the source's blocky pixel grid, or deliberate dithering, as a protected/intentional-
  artifact texture.** This was the v0.1/v0.2 goal and is explicitly reversed — see the pivot note
  above. Dithering is now treated like any other source pattern to be smoothed into the gradient or
  blend it was approximating, the same way xBRZ and Omniscale already treat it.
- Full spline/vector-file output (Depixelizing Pixel Art-style vectorization to an actual
  resolution-independent format) — this stays a real-time raster shader; "vector-faithful" describes
  the reconstruction goal, not the output representation.
- 3D/polygonal retro content (PS1/N64/Saturn) — 2D sprite/tile-based systems only for v1.
- General photoreal ML super-resolution.
- Replacing CRT/bezel simulation shaders (Mega Bezel, CRT-Royale) — this composes with them, not
  competes.

## 4. Current-State Survey (baseline to beat)

Numbers are this project's own measurements (`tools/gold_eval/report.md`), not vendor claims — the
vector-regime score on the two hardest hand-picked shapes (a sharp corner, a continuous curve),
scored against a real smooth ground truth.

| Shader/Algorithm | Type | Vector-regime score (V-corner / O-ring) | Known weaknesses |
|---|---|---|---|
| Nearest-neighbour | Passthrough | 81.0% / 82.3% | The mandatory control — zero smoothing, honest baseline |
| **xBRZ** | CPU pattern-matching, GPLv3 | **93.4% / 95.2%** — current leader | Not GPU-native; copyleft (clean-room only, `docs/licensing.md`) |
| SABR | Slang, GPLv2+ | 90.1% / 91.3% | Copyleft (clean-room only) |
| ScaleFX | Multi-pass slang, MIT | 88.9% / 87.8% | 4-5 passes, GPU-heavy |
| Omniscale | Slang, MIT | 81.8% / 85.4% | **Visibly rounds glyph/sharp corners** — the concrete failure this project targets |
| This project's earlier prototype (`mobile-lite.slang`) | 1-pass slang | 80.5% / 82.9% | Ties/loses to nearest-neighbour — built for a different goal, see §9 |

**xBRZ is the bar, and the most legally constrained** (GPLv3, no exception covers this project —
`docs/licensing.md`): its approach may be studied and understood, never ported or transliterated.
Omniscale and ScaleFX are MIT and may be read/adapted directly.

## 5. Functional Requirements

1. **FR1 — Input handling.** Accept native core-resolution framebuffer input via the libretro/slang
   filter-chain `Source` texture; must work regardless of core-reported `base_width`/`base_height`,
   including mid-session geometry changes (SNES Mode 7, GBA layer changes).

2. **FR2 — Edge-directed continuous-shape reconstruction, applied uniformly.** Classify local edge/
   curve geometry and reconstruct it as a continuous shape (diagonals as diagonals, curves as curves,
   corners as corners), in the tradition of HQx/xBRZ/Omniscale pattern-based reconstruction. This
   applies to *all* content the same way — there is no separate content-class routing to a nearest-
   neighbour or "protect the pixels" path. (Contrast with v0.2's FR2, which special-cased text and
   dithering; both are retired, §3.)

3. **FR3 — Text/glyph fidelity is a first-class, separately measured requirement**, not an assumed
   side effect of FR2. Score dedicated text/letterform content (`tools/gold_eval`'s V/O hard cases,
   plus real bitmap-font dialogue/menu/HUD content) through the same reconstruction pipeline as
   everything else, and treat the result as a primary pass/fail gate: must match or beat xBRZ's
   score, and must clearly beat Omniscale's specific corner-rounding failure (§4), across at least
   three distinct bitmap font styles (thin sans-serif, outlined/drop-shadow, blocky).

4. **FR4 — Ship as a standard `.slangp` preset pack**, installable the same way as existing
   community shader packs (`shaders/shaders_slang/argus/`), compatible with RetroArch and
   librashader. A parallel legacy `.glslp`/`.glsl` pack for pre-slang installs is a secondary goal,
   ported once the primary pack's algorithm is settled — not maintained in lockstep during redesign.

5. **FR5 — Parameterization.** Expose tunables via `#pragma parameter` (edge threshold, sharpen
   amount) so users can tune to taste. Per-console dither-convention tuning (v0.2's system-profile
   axis) is retired along with dither preservation; one reconstruction profile should work across
   systems unless evidence says otherwise.

6. **FR6 — Aspect ratio / non-square pixel correctness.** Presets must respect each console's native
   pixel aspect ratio rather than assuming square pixels.

7. **FR7 — No core modification.** Must work purely as a shader preset.

## 6. Non-Functional Requirements

- **Performance is real, but secondary to correctness right now.** v0.2's mobile-tier pass-budget
  architecture (LUT + wide-kernel classifier fused into one pass) is not carried forward as-is — it
  served the now-retired dither/text classification, and its one shipped instance had a real,
  evidenced GPU anti-pattern (25-tap arrays read back across five separate loops, a register-
  spilling hazard — `docs/backlog-status.md`). A new performance budget gets defined once the
  reconstruction algorithm is redesigned and validated against §4's bar, not before.
- **Backend portability:** must compile/run correctly on GL, Vulkan, D3D10/11/12, and Metal without
  backend-specific forks. Validated continuously via the existing compile gate (`tools/compile_gate/`).
- **No core modification; run-ahead/rewind compatible** if/when a temporal term is reintroduced (none
  is required by this revision — §8).
- **Latency:** no perceptible added input lag.

## 7. Validation & Test Plan

The evaluation harness built under v0.2 is unaffected by this pivot and remains the primary
validation mechanism:

- **`tools/gold_eval`** — the primary quality gate. V-corner and O-ring hard cases, scored against
  both a `vector` regime (a true smooth source exists) and an `8bit` regime (genuinely blocky, no
  hidden smooth source). §4's numbers come from here. A candidate reconstruction must move the
  vector-regime score toward xBRZ's without collapsing the 8bit-regime score below nearest-
  neighbour's honest floor on content that really is just blocky.
- **`tools/eval_metric`** — ground-truth IoU scoring against an 8x-supersampled reference, including
  real RPG dialogue/letterform content (`rpg_text_eval.py`).
- **`tools/comparison`** — runs nearest-neighbour, Omniscale, SABR, ScaleFX, and xBRZ (clean-room
  only for the copyleft three, `docs/licensing.md`) through the same render harness for direct,
  same-conditions comparison.
- **`tools/render_harness`** — headless golden-image regression; gates every commit.
- **`tools/ab_compare`** — perceptual spot-check for intentional changes, not the primary gate.
- **Real RetroArch testing** (`docs/retroarch-testing.md`) remains the final sanity check — this
  pivot exists *because* real-hardware/real-content testing caught what narrower synthetic tests
  missed.

## 8. Open Questions

- What reconstruction technique moves the vector-regime score from 80.5%/82.9% (current prototype)
  toward xBRZ's 93.4%/95.2%, while staying implementable clean-room (xBRZ itself can't be ported
  directly — GPLv3)? Candidates to study from public descriptions/MIT sources: xBRZ's own published
  rule-set writeups, Omniscale's approach with a corner-rounding fix, ScaleFX's contour-following.
- Is a dedicated glyph-shape prior (recognizing "this is probably a font stroke" and reconstructing
  accordingly) still useful for FR3 now that it's an accuracy target rather than a routing decision —
  or does a strong general reconstruction rule already get there?
- Does a temporal stabilization term (v0.2's FR4) still belong in v1, or is it out of scope until the
  core reconstruction is solved?
- What's the actual performance cost of a reconstruction good enough to hit §4's bar, once real
  hardware (still blocked — `docs/backlog-status.md`) is available to measure it?

## 9. What changed from v0.2, and why

v0.2's shipped prototype (`shaders/shaders_slang/argus/shaders/mobile-lite.slang`) implemented: a
four-class region classifier (hard-edge / dither / AA-gradient / text-glyph), a dither-preservation
reconstruction rule, and a text-to-nearest-neighbour protection rule. Two independent pieces of
evidence showed this was the wrong goal, not just an under-tuned implementation:

1. **`tools/gold_eval`** (built specifically to settle this): on the `vector` regime, the prototype
   ties/loses to nearest-neighbour on both hard shapes while every real competitor (xBRZ, SABR,
   ScaleFX) clears a 9-13 point margin over it. It only wins on the `8bit` regime — content that was
   never meant to be smoothed, which real game content isn't purely made of.
2. **Real RetroArch testing** by the project owner: "argus is slow and nearly unplayable... argus has
   no benefit whatsoever to smoothing... xbrz looks great." Both the performance and quality
   complaints held up under investigation (`docs/backlog-status.md`).

This revision is the direct response: drop the preservation goal, keep the evaluation harness that
caught the problem, and redesign the reconstruction algorithm against the corrected target in §2-4.
