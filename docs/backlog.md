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

## What's next (v0.3, Phase 1)

Not yet started. See `docs/requirements.md` §8 for the open design questions.

1. **Study xBRZ's rule set from public descriptions (not its GPLv3 source), and Omniscale/ScaleFX's
   source directly (MIT).** Identify why Omniscale specifically rounds sharp corners, and why xBRZ
   doesn't — that gap is the concrete target.
2. **Redesign the edge/curve reconstruction rule** against `tools/gold_eval`'s vector-regime metric as
   the primary target, checked against the 8bit-regime metric as a regression guard (don't smooth
   content that has no smooth source, but don't special-case it either — let the same rule handle it
   correctly by classifying "already flat/blocky" as a legitimate edge-geometry outcome, not a
   separate protected path).
3. **Validate text/glyph fidelity (FR3) as its own gate**, using the existing real bitmap-font RPG
   content (`tools/comparison/generate_rpg_text.py`) plus at least two more font styles not yet in
   the corpus (outlined/drop-shadow, blocky).
4. **Re-fuse into a shipped pass once the algorithm clears the bar**, this time checking compiled
   output for the register-spilling pattern `docs/backlog-status.md` documents, not just source-level
   review.
5. **Re-run real RetroArch A/B testing** (`docs/retroarch-testing.md`) before calling it done — that's
   what caught the previous miss, and remains the final check, not the synthetic harness alone.

Still blocked on external resources, unchanged by the pivot: a physical ARM reference handheld
(needed for real frame-time/bandwidth measurement) and a real-game redistributable content corpus
beyond what's synthetic/RPG-generated.
