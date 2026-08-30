# T-004 — Two-level classifier feasibility spike

Resolves the Phase-0 highest-risk ticket in [`docs/backlog.md`](../../docs/backlog.md#t-004--spike-two-level-classifier-feasibility-️-highest-risk).
Offline CPU/numpy prototype, not a shader — see [`classify.py`](classify.py). Reproduce with:

```
python3 tools/patterns/generate_patterns.py
python3 tools/patterns/generate_text_sets.py
python3 tools/classifier_spike/classify.py
```

## Result: dither vs. AA-gradient separation — **PASS**

This is the ticket's explicit pass/fail axis (§6a.3, docs/review-notes.md B2): can a 5×5
wide-kernel statistic set tell intentional ordered dither (class b) apart from an already
anti-aliased gradient (class c), given both use a similarly narrow band of colors and
similar local contrast?

| Metric | Score | Threshold |
|---|---|---|
| Dithered transition zones correctly labelled (b) | 0.908 | — |
| AA-gradient transition zones correctly labelled (c) | 0.906 | — |
| **Separation score** (min of the two) | **0.906** | ≥ 0.85 |

The discriminating signal is **checkerboard autocorrelation** — the window's projection onto
the Nyquist-diagonal basis `(-1)^(dx+dy)`, normalized by local spread. Ordered dither produces
strong 1px-period alternation (measured p10=0.199 across the corpus); true AA blending does not
(measured p90=0.086). **Unique-color count** corroborates it independently: dithered windows see
exactly 2 colors, AA windows see 3-4. The two-level decomposition in §6a.3 is confirmed workable —
no architecture change is required, and Phase 1 can proceed on this basis.

One methodology note: the first pattern draft (a single slow whole-image gradient) was **not** a
valid test — over a 256px span, a 5×5 window is locally almost flat regardless of dither vs. AA,
so both classes scored near-identical low variance and the test measured nothing. The corpus
generator (`tools/patterns/generate_patterns.py`) was corrected to use many short (4px) local
transition zones with an accompanying ground-truth mask (`*_mask.png`), which is the regime real
AA-vs-dither ambiguity actually occurs in. Recorded here since it's a trap the T-007/T-011 corpus
work should avoid repeating with real captured content.

## Result: other FR2 classes — informative, not gating

| Region | Metric | Score |
|---|---|---|
| Hard-edge/flat (a) | Checkerboard-transparency background correctly labelled (a) | 0.974 |
| Dither (b) | Checkerboard-transparency block correctly labelled (b) | 1.000 |
| Hard edges generally | Diagonal-sweep pixels *not* misread as dither | 0.982 |
| Thin stroke (d) | Text-positive foreground pixels correctly labelled (d) | 0.650 |
| Thin stroke (d) | Text-negative foreground pixels *incorrectly* labelled (d) | 0.808 |

Classes (a) and (b) separate cleanly from everything else tested. Class (d) does not yet —
recorded honestly rather than tuned to look better, since T-010 exists specifically so this
doesn't get glossed over.

**Why (d) is weak with this statistic set:** the only signal tried for "thin stroke" is a
local run-length estimate (stroke width) inside the same 5×5 window. Within a 5-pixel window, a
short glyph stroke and a long straight architectural grid line of the same 1px width are
**locally identical** — the window simply can't see far enough to tell "this stroke ends soon"
from "this line keeps going." That's not a bug in this prototype; it's the exact failure mode
§5 FR2 already names as well-documented for edge-reconstruction algorithms on text, now confirmed
to also apply to *detecting* text with a small kernel, not just reconstructing it. Fur/hair strokes
score similarly for the same reason (short, thin, high-contrast, same local footprint as a serif).

This does not block Phase 1 — T-016/T-017 own class (d) and are scoped with their own gate
(T-009 positive-set legibility + T-010 negative-set false-positive rate, evaluated together).
Recommendation carried forward to those tickets: stroke-width alone is insufficient; combine it
with the 3×3 LUT topology (glyph strokes have more corners/junctions per unit length than a
straight architectural line) or accept a wider receptive field specifically for class-(d)
candidates. Flagging now so it isn't rediscovered cold when T-017 opens.

## Statistic set and ALU cost (per pixel, 5×5 window, 25 taps already fetched)

| Statistic | Approx. op count | GPU-friendly as specified? |
|---|---|---|
| Mean | ~25 (24 add + 1 mul) | Yes |
| Variance | ~75 (reuses mean; 25 sub, 25 mul, 24 add, 1 mul) | Yes |
| Checkerboard autocorrelation | ~75 (25 signed-mul via sign flip, 24 add, 25 abs+add, 1 div) | Yes — sign flip is free (XOR the exponent bit or precomputed ±1 constant per tap position, no branch) |
| Stroke-width (run-length through center) | ~16 compares/adds per axis, 2 axes ≈ 32, plus 1 min | Yes, but see below |
| **Unique-color count** | **O(k²) pairwise compares ≈ 300** for k=25 taps, plus 25×3 quantization ops | **No** — this is the one statistic in the set that is not divergence-free/cheap as literally specified. A brute-force distinct-count needs pairwise comparison or a sort; neither is a good fit for FS ALU. |

**Finding to carry into T-015:** unique-color count as specified ("unique-color count") is not
directly implementable at the stated ALU budget. A cheap GPU-friendly proxy is needed — options
worth prototyping in T-015: a small fixed-size hash/bitmask accumulator (OR quantized color bits
into an int, popcount at the end) rather than literal distinct-counting; or dropping unique-color
as a standalone statistic and folding its signal into the checkerboard/variance pair, since in this
spike unique-color count was corroborating rather than load-bearing (checkerboard autocorrelation
alone already achieves the separation). Recommend T-015 prototype the bitmask-popcount version and
confirm it doesn't change the classification boundary before committing to it.

## Conclusion

The §6a.3 two-level decomposition is **feasible** on its stated highest-risk axis (dither vs. AA
gradient) and Phase 1 (T-014 onward) can proceed without an architecture change. Two concrete
follow-ups are handed to downstream tickets rather than blocking this one: class-(d) text
detection needs a signal beyond local stroke-width (→ T-016/T-017), and unique-color-count needs a
cheaper GPU-friendly formulation (→ T-015).
