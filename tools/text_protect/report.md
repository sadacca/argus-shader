# T-017 — Text/glyph protection reconstruction rule (class d)

Resolves the reconstruction-rule half of
[T-017](../../docs/backlog.md#t-017--textglyph-protection-path-class-d) in
`docs/backlog.md`; leaves the classifier-separability half open and tracked
as new scope in **T-041** (see "What's still open" below and
`docs/backlog.md`). Builds on T-015/T-016's already-verified classifier the
same way T-019's dither rule does. See `text_debug.slang` (the shader),
`text_reference.py` (the CPU model, with the rule's rationale in its module
docstring), and `verify_gpu.py` (renders through T-003's harness, checks
numeric parity, and checks both T-017 acceptance criteria against actual
rendered output). Reproduce with:

```
python3 tools/text_protect/verify_gpu.py
```

## Result

```
[1] legibility (protected)   mean=0.651   (nearest-neighbour baseline = 1.000)
    legibility (unprotected) mean=0.002   (no class-d special case at all)
    PASS — the routing measurably helps: without it, legibility on this
    corpus collapses from 0.651 to 0.002 (near-total loss).
[2] false-positive rate on text_negative: mean=0.808 — measured, reported,
    not gated. See Finding 1: this is a pre-existing T-016 classification
    limit, not something this ticket's reconstruction rule can fix, and no
    threshold is being asserted as "passing" against it.
```

## The rule

For class-(d) pixels (thin high-contrast monochrome stroke, per T-016's
existing decision), output the exact source color — no interpolation at
all, not even T-019's tunable blend. FR2 doesn't ask for a dial here the way
dither preservation gets one; it asks for a hard guarantee that a font
stroke never touches diagonal/edge reconstruction, because a 1-2px stroke
genuinely doesn't carry enough neighborhood context for that math to work
(`docs/requirements.md` FR2's own stated reason, not a assumption added
here). Non-class-(d) pixels fall back to the same local-mean placeholder
`dither_debug.slang` uses for its own non-dither pixels — not this ticket's
job to build classes (a)/(c)'s real reconstruction.

Criterion 1 was checked against a real comparison baseline
("unprotected": the local-mean placeholder applied to every pixel, i.e. what
this project looked like before T-017 added a class-(d) special case) rather
than only asserting "protected == nearest-neighbour on protected pixels,"
which would have been true by construction and not actually demonstrated
anything. The gap is dramatic — 0.651 vs 0.002 — because the local-mean
placeholder is a genuinely destructive stand-in for "diagonal reconstruction
with no text awareness," which is exactly the failure mode FR2 names.

## Finding 1 — the false-positive rate is a real, measured classifier-separability limit, not a tuning gap this ticket can close

`docs/backlog.md`'s T-010 ticket deliberately built `text_negative` (fur/hair,
architectural line grids, weapon-outline silhouettes) to share the
thin-high-contrast-stroke signature with real glyphs, specifically so a
classifier that over-triggers on stroke width alone couldn't look like it
was succeeding. Before writing this ticket's reconstruction rule, the actual
separability was checked directly against the corpus (not assumed):

| category | foreground pixels routed to class (d) |
|---|---|
| `architecture_*` | 88.5-90.7% |
| `weapon_outline_*` | 98.6% |
| `fur_hair_*` | 52.6-54.8% |
| **mean (T-010's false-positive rate)** | **80.8%** |

This number is unchanged from `tools/classifier_spike/spike_report.md`'s own
T-004-era measurement — confirming the limitation is real and inherited, not
a regression this ticket introduced. A per-category breakdown of the
underlying wide-kernel statistics on each corpus's foreground pixels was
also checked, specifically looking for *any* threshold on the four existing
statistics (variance, checkerboard-autocorrelation, luma-bin popcount,
stroke-width) that could separate `text_negative` from `text_positive`:

| category (sample) | stroke_width<=2 fraction | mean local variance | popcount | checker_autocorr |
|---|---|---|---|---|
| `text_positive/blocky` | 0.36 | 12228-12272 | 2.00 | 0.076 |
| `text_negative/weapon_outline` | 0.99 | 10781 | 2.00 | 0.039 |
| `text_negative/architecture` | 0.91 | 3822 | 2.00 | 0.077 |
| `text_negative/fur_hair` | 0.97-1.00 | 2852-2963 | 2.00 | 0.131-0.136 |

Variance magnitude is close between `blocky` and `weapon_outline` (both
high-contrast strokes on a flat background — variance mostly reflects
color-distance, not shape), and `checkerboard_autocorr`/popcount don't
separate any pair here either. **No threshold on this statistic set
separates these categories**, because the categories were built to share
the exact signature these statistics measure (stroke width, over a 5x5
window, on a flat background) — this confirms, with real numbers instead of
a guess, `docs/requirements.md`'s own claim that "font stroke widths (1-2
source pixels) don't carry enough neighborhood context for edge-
reconstruction algorithms to classify correctly." A 5x5 window has no way to
see that a stroke sits in a periodic architectural grid, follows an organic
fur curve, or belongs to a character cell — that needs either a wider
neighborhood (against this project's own performance-driven kernel-size
decision, §6a.3) or a different kind of signal entirely (e.g. T-014's LUT
topology, connectivity, or grid-position information not yet fused in).

**This is exactly the risk T-004's spike report already carried forward**
("class (d) text-detection weakness... carried forward as a finding, not a
blocker") and T-010 explicitly deferred ("no target threshold agreed yet
since class (d) tuning is T-016/T-017's job"). Given the evidence above, the
honest call is: **no threshold on the current statistic set can be "agreed"
as passing**, because none exists that would. Asserting one anyway would
misrepresent what's actually been verified — this project's own documented
discipline is against exactly that.

## Why this doesn't block T-017's reconstruction rule from being correct

Unlike a false-negative on a truly *destructive* rule, misrouting
non-text art to class (d)'s nearest-preserving reconstruction is not itself
a correctness bug: nearest-neighbour sampling is always a safe fallback —
worse than an ideal edge-aware reconstruction would have been on that
content, but never wrong or visually broken the way over-smoothing a real
glyph would be. So while the classifier's separability is a genuine,
tracked limitation, it does not make this ticket's actual deliverable (the
class-(d) reconstruction rule itself, and its measured benefit when correctly
triggered) incorrect or unverified.

## What's still open

- **T-041 (new ticket, tracked in `docs/backlog.md`)**: improve class-(d)
  separability beyond the current 5x5 wide-kernel statistic set. Candidate
  directions worth investigating, none attempted here since they're each a
  real design change, not a tuning tweak: (a) a wider secondary kernel
  specifically for the density/periodicity check the 5x5 window can't see
  (architecture's grid spacing, fur's local stroke density) — in tension
  with §6a.3's ALU-budget-driven small-kernel decision; (b) fusing T-014's
  LUT topology (already built, not yet consumed by T-016) for
  connectivity/grid-alignment cues; (c) accepting the current false-positive
  rate as a permanent tradeoff and leaning on this ticket's finding that
  nearest-preserving reconstruction is a safe (if suboptimal) fallback on
  misrouted content, formalizing that as the project's actual position
  instead of an open question.
- Same scope boundary as T-019: this debug shader runs at native resolution
  (scale 1.0) with an unfiltered/local-mean placeholder standing in for
  classes (a)/(c); real upscaling and the other classes' reconstruction are
  T-018/T-020's job.
