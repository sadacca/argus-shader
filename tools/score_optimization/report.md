# T-046 — iterative score-optimization experiments

Full writeup and conclusions: `docs/backlog.md`'s T-046 entry and `docs/backlog-status.md`'s
2026-09-19 update. This file holds the raw numbers.

## Experiment 1 — disable T-018 edge reconstruction (`variant_no_edge_recon.slang`)

| | rpg_dialogue_box | rpg_letters |
|---|---:|---:|
| baseline (shipped) | 82.00% | 89.02% |
| edge reconstruction disabled | 82.00% (unchanged — never triggers on this content) | 88.31% (**worse**) |

## Experiment 2 — disable T-017 text/stroke protection, ceiling probe (`variant_no_stroke_protect.slang`)

| | rpg_dialogue_box | rpg_letters |
|---|---:|---:|
| baseline (shipped) | 82.00% | 89.02% |
| stroke protection disabled | 81.72% (**worse**) | 89.03% (~unchanged) |

Conclusion: the IoU gap to xBRZ/SABR/ScaleFX is not explained by text protection costing score —
disabling it doesn't recover any meaningful ground, and slightly loses some.

## Experiment 3 — sweep T-018's blend-steepness constant (`t = clamp(dist * N, 0, 1)`, shipped `N=2.0`)

Full sweep, scored against the RPG-content IoU rubric (`tools/score_optimization/score_variant.py`):

| N | rpg_dialogue_box | rpg_letters |
|---:|---:|---:|
| 0.5 | 82.76% | 88.86% |
| 0.75 | 83.36% | 89.25% |
| **1.0** | **83.79%** | 89.62% |
| **1.25** | 83.76% | **89.76%** |
| 1.5 | 83.25% | 89.53% |
| **2.0 (shipped)** | 82.00% | 89.02% |
| 4.0 | 79.40% | 87.96% |

`N≈1.0-1.25` looks like a clear win on this metric (+1.7-1.8pp). **Cross-checked against
`tools/edge_reconstruct/verify_gpu.py`'s sub-pixel edge-position error** (diagonal sweep, 15°-75°
angles, analytic ground truth — T-018's own established metric) before trusting it:

| N | mean sub-pixel error (px) | vs. nearest-neighbour | vs. Omniscale (5 scales) |
|---:|---:|---|---|
| **2.0 (shipped)** | **1.051** | beats it | wins 1/5 |
| 1.0 | 1.539 | **loses to it** | wins 0/5 |
| 4.0 | 1.164 | beats it | (not re-run) |

`N=1.0` — the value the RPG-content rubric preferred — is a **46% regression** on the metric that
actually spans a realistic range of edge angles. `N=2.0` is confirmed as a genuine, already-
near-optimal choice; verified the harness reproduces T-018's own report numbers exactly at `N=2.0`
before drawing this conclusion, so it isn't a measurement artifact.

**Takeaway**: the RPG-content IoU rubric is useful but narrow (dominated by near-axis-aligned box-
border and text-stroke edges) — tune against it *and* the diagonal-sweep metric together, never one
alone, for anything touching T-018's edge reconstruction.
