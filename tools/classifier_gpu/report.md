# T-015/T-016 — GPU classifier statistics and region classification

Resolves [T-015](../../docs/backlog.md#t-015--wide-kernel-scalar-statistics) and
[T-016](../../docs/backlog.md#t-016--fr2-four-class-region-classifier) in
`docs/backlog.md`. GLSL port of `tools/classifier_spike/classify.py` (T-004) — see
`classify_debug.slang` (the shader), `reference.py` (the CPU model it's checked against,
itself a variant of T-004's `classify.py` with the unique-color-count replacement T-004
flagged as needed), and `verify_gpu.py` (renders the shader through T-003's harness and
checks both against the CPU model). Reproduce with:

```
python3 tools/classifier_gpu/reference.py   # CPU-only, fast iteration
python3 tools/classifier_gpu/verify_gpu.py  # renders through the real GLES path, slower
```

## Result: T-004's dither-vs-gradient separation bar — **PASS, unchanged**

0.906 (min of 0.908/0.906), identical to T-004's own 0.906 — the checkerboard-autocorrelation
signal that carries this result is untouched by anything below; only the unique-color-count
side statistic changed.

## Finding 1 — unique-color-count's GPU-friendly replacement needs 32 bins, not 8

T-004's spike report flagged that literal unique-color counting isn't ALU-cheap on a GPU and
recommended prototyping a bitmask/popcount proxy over quantized luma bins. The first version
tried here (8 bins, width 32) preserved the T-004 gating metric exactly but silently broke
something T-004 didn't gate on: **text-positive stroke recall dropped from 0.650 to 0.378**,
traced to this corpus's "outlined" glyph style, whose outline color (`[0,0,0]`) and
background color (`[12,12,20]`) differ by only ~13 luma units — well inside an 8-bin (width-32)
bucket, so they collapsed into the same bin and produced false dither-positives on 81% of that
style's foreground pixels. **32 bins (width 8)** resolves this pair and restores 0.650 exactly,
at identical ALU cost (`mask |= 1 << bin; bitCount(mask)` — the bin count only changes the
shift amount, not the number of operations). 32 is also the practical ceiling for this
technique: it's the full width of a single GLSL `int`, so going wider needs a second mask word
for no benefit at 32. Shipped at 32 bins; see `reference.py`'s `N_LUMA_BINS` comment.

## Finding 2 — the checkerboard-autocorrelation ratio is a 0/0-like indeterminate form on flat windows

`checker_raw / spread` is mathematically 0/0 on a perfectly flat 5×5 window (both numerator and
denominator are the same "no local variation" signal). T-004's original CPU implementation
happens to hit exact float cancellation when every tap is sourced from the same uint8 pixel
value (so the ratio comes out exactly 0), which made this invisible in T-004's own spike. It is
not invisible on this project's actual GLES render path: **77% of pixels in one test image**
had genuinely flat CPU-side windows where the GPU's different summation order produced a
noise-dominated ratio (measured 0.03–0.10) instead of 0 — close enough to the 0.15 dither
threshold to be a real robustness risk on real hardware, not just a CPU/GPU parity nuisance.
Fixed with a branchless signal floor (`step(MIN_SPREAD, spread)`, `MIN_SPREAD = 0.5` luma
units — ~1000× the observed noise floor, far below any real dithered-pattern spread) applied
identically in both `reference.py` and the shader. Re-verified: T-004's separation score is
unchanged, and the flat-region false-positive noise is gone.

## Finding 3 — the `mediump` variance accumulator can overflow on real hardware

The variance accumulator sums up to 25 terms of `(delta-luma)^2`, each up to `255^2 = 65025`;
the sum can reach ~1.6M, which overflows real `fp16` `mediump` (max ~65504) even though it
can't be observed failing in *this* environment — Mesa's software GLES stack likely executes
`mediump` as `fp32` internally, so this can't be verified as an actual runtime failure here,
only reasoned about from the numbers. Declared the statistics-accumulation block `highp`
rather than ship an unverified assumption; **T-015's "mediump-safe" acceptance box is
therefore only partially closed** — see the ticket note in `docs/backlog.md`. The other three
statistics (checkerboard ratio ~[0,1], popcount [0,32], stroke run-length [0,99]) are all
small enough in magnitude to be `mediump`-safe by construction and are candidates to downgrade
from `highp` for performance once this lands in the perf-tuned fused pass (T-020) — not done
here, since this shader's job is correctness verification, not performance tuning.

## Finding 4 — `texelFetch` needs manual edge-clamping

`texelFetch` returns undefined values outside `[0, textureSize)`; the CPU reference edge-pads
(`np.pad(mode="edge")`). Fixed with `clamp(coord + offset, ivec2(0), sourceSize - 1)` per tap.
Without this, variance/checkerboard/stroke-width all diverged from the CPU reference on
roughly a 2-pixel border band around every image (~3-4% of pixels on a 256×240 image), which
is exactly the footprint you'd expect from a 5×5 kernel's unclamped edge.

## Finding 5 (informational, not a bug) — stroke-width's raw value diverges near flat/background windows, but final classification doesn't

The foreground test (`L[i] >= mean`) is a hard tie on a background-dominated window, where the
center pixel's luma is very close to the window mean by construction. CPU/GPU float summation
order disagree on which side of that tie a near-equal value lands (same underlying mechanism as
Finding 2, but on a boolean rather than a ratio, so it isn't fixable the same way — there's no
"close enough to flat" floor for a per-tap boolean test the way there is for a window-level
spread ratio). Measured: this flips the *raw* `stroke_width` value often (a real run-length on
one side, the 99.0 "not foreground" sentinel on the other), but essentially never flips the
*final classification*, because both outcomes land on the same side of `STROKE_WIDTH_MAX`.
Checked directly: 0 of 32,616 raw-value mismatches on the worst-case test image changed the
final label. `verify_gpu.py` treats stroke-width parity as informational for exactly this
reason and gates on final-label agreement instead, which is the claim that actually matters.

## Finding 6 (documented, not fixed) — one corpus category sits exactly on a threshold

`text_negative/architecture_*.png`'s regularly-spaced lines produce a checkerboard-autocorrelation
value that CPU float arithmetic computes as `0.14999999` — a hair under the `0.15` dither
threshold purely from summation-order rounding, not a meaningfully different true value. This
is what comparing two independent floating-point implementations at a knife-edge decision
boundary looks like: no amount of careful arithmetic removes it, because the underlying
quantity genuinely is (to float precision) equal to the threshold. `verify_gpu.py` reports this
category's label-agreement rate separately (mean 2.9%, max 9.75%) rather than either hiding it
in a shared average or loosening the general tolerance to accommodate it.

## ALU cost (per pixel, 5×5 window, 25 taps)

| Stage | Approx. op count | Notes |
|---|---|---|
| `luma()` × 25 taps | ~150 | 3 mul + 2 add (dot) + 1 mul (×255), ×25 |
| Mean | ~26 | 25 add + 1 div |
| Variance | ~75 | matches T-004's estimate |
| Checkerboard autocorrelation | ~130 | includes the `step()` signal-floor guard (Finding 2) |
| Unique-color-count proxy (32-bin popcount) | ~100 | 25 × (div, clamp, shift, or) + 1 `bitCount` |
| Stroke-width (unrolled) | ~20 | fixed small op count, matches T-004's estimate |
| **Total** | **~500** | texture fetches (25 `texelFetch` + edge clamp) not counted above |

## What's still open

- T-015's "ALU op count... measured and recorded" box: closed by the table above (estimated
  from source, not profiled on real hardware — no profiling tool available in this
  environment).
- T-015's "mediump-safe" box: partially closed — see Finding 3. Full closure needs either real
  mobile hardware or a software GLES implementation that actually emulates `fp16` `mediump`
  precision loss, neither available here.
- This is a debug/verification shader (`classify_debug.slang`), not yet fused into a shipped
  preset — that's T-020's job, combined with T-017/T-018/T-019's reconstruction logic. T-016's
  own acceptance boxes about "no divergent branching in the hot path" and "operates per-region
  within one shader" are written with that eventual fused pass in mind; this file establishes
  the verified math those boxes will apply to, not the final hot-path implementation itself.
