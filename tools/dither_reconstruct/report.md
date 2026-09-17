# T-019 — Dither preservation reconstruction rule

Resolves [T-019](../../docs/backlog.md#t-019--dither-preservation-rule) in
`docs/backlog.md`. Builds on T-015/T-016's already-verified classifier
(`tools/classifier_gpu/`) rather than re-deriving classification — this
ticket is only the reconstruction rule applied to whatever the classifier
already calls class (b). See `dither_debug.slang` (the shader),
`dither_reference.py` (the CPU model, with the rule's full rationale in its
module docstring), `generate_soft_dither.py` (new test content, see Finding
1), and `verify_gpu.py` (renders the shader through T-003's harness, checks
numeric parity against the CPU model, and checks all three of T-019's
acceptance criteria directly against rendered output). Reproduce with:

```
python3 tools/dither_reconstruct/generate_soft_dither.py  # regenerate corpus/synthetic/dither_soft/
python3 tools/dither_reconstruct/verify_gpu.py             # renders through the real GLES path
```

## Result: all three T-019 acceptance criteria — **PASS**

```
[1] checkerboard-transparency, strength=1.0: mean |rendered-source| over dither region = 0.000  PASS
[2] dither_ramp (Genesis-style, top half), strength=1.0: mean |rendered-source| = 0.000          PASS
[3] strength=0.5: hard(checkerboard)=1.472  soft(dither_soft)=2.999  ratio=2.04x                 PASS
```

## The rule

Each class-(b) pixel blends between its own exact source color (full
preservation) and its local 5×5-window mean color (what a naive
smoothing/upscale pass would produce instead):

```
hardness     = clamp(spread / SPREAD_HARD_REF, 0, 1)   # SPREAD_HARD_REF = 20 luma units
blend_amount = (1 - hardness) * (1 - ARGUS_DITHER_STRENGTH)
output       = mix(source_color, local_mean_color, blend_amount)
```

`spread` (mean absolute luma deviation from the window mean) is already
computed by the classifier as the checkerboard-autocorrelation ratio's
denominator (`classify_debug.slang`'s 0/0 guard, T-015 Finding 2) — reused
here as a "how far apart are the two dithered colors" signal, not
recomputed. At the FR5 default (`ARGUS_DITHER_STRENGTH = 1.0`,
full preservation), `blend_amount` is always 0 regardless of hardness:
every dither pixel is exactly preserved by default. Turning strength down
lets genuinely soft/low-contrast dither degrade into ordinary smoothing
faster than a stark high-contrast checkerboard does at the same setting —
blending two very different colors into their average produces an
obviously-wrong muddy color (a visible artifact, not just "less crisp"),
so hardness acts as a floor against that regardless of the user's strength
setting.

Non-dither pixels pass through unchanged in this debug shader — T-019 only
defines class (b)'s rule; classes (a)/(c)/(d) get their own reconstruction
in T-018/T-017, and only get fused together with real neighbor-blending
behavior for the non-dither path in T-020. Building a placeholder
non-dither reconstruction here would misrepresent what's actually been
verified.

## Finding 1 — the existing corpus has no "soft" (SNES-style) dither sample

`docs/backlog.md`'s T-019 acceptance criteria explicitly want behavior to
differ between "NES-style hard dither" and "SNES-style blending," but every
existing dither sample (`checkerboard_transparency`, `dither_ramp`'s top
half) uses high-contrast color pairs — measured `spread` of ~17 (checkerboard,
colors ~36 luma apart) up to ~45-76 (dither_ramp, colors ~157 luma apart)
across the corpus. `docs/requirements.md` §5 FR9 clarifies what "SNES-style"
actually refers to: SNES's larger palette means it relies less on manual
dithering to begin with, and prefers real hardware alpha blending — which,
when used directly, wouldn't be classified as dither (class b) at all, so
there's no reconstruction-rule question to test there. What *is* worth
testing is the case where SNES-era content still uses ordered dithering, but
between much closer palette entries than NES/Genesis's typical high-contrast
pairs.

`generate_soft_dither.py` adds exactly that: the same Bayer-4×4 ordered
technique as the existing corpus, between two colors ~20 luma units apart
instead of ~36-157. Measured `spread` in the resulting dither region: 7.7,
clearly separated from the existing hard samples. This is new, additive test
content scoped to this ticket (`corpus/synthetic/dither_soft/`), not a
retroactive change to T-008's corpus, which stays focused on the
dither-vs-gradient classification axis this reconstruction rule doesn't
touch.

## Finding 2 — `SPREAD_HARD_REF = 20` was chosen empirically against the corpus's own measured spread distribution, not guessed

Before writing the rule, `dither_reference.py`'s `spread` field (added to
`classifier_gpu/reference.py`'s `compute_stats()` return dict — additive,
doesn't change T-015/T-016's already-verified behavior) was measured across
every existing dither sample:

| corpus | spread mean | spread max |
|---|---|---|
| `checkerboard_transparency` (all systems) | ~17.0-17.4 | 18.0 |
| `dither_ramp` top half (all systems) | ~45.0-55.2 | 76.7 |
| `dither_soft` (new, Finding 1) | 7.7 | 7.7 |

20 sits just above the checkerboard case (so it reads as "hard," hardness
~0.86-0.90, matching intent) while `dither_ramp`'s more extreme color pairs
clamp to hardness 1.0 (fully hard, as expected for the most extreme case in
the corpus) and the new soft sample lands at hardness ~0.39 — enough
separation that criterion 3's measured 2.04x ratio isn't a knife-edge
result sensitive to small numeric noise (unlike, e.g., T-016's documented
`text_negative/architecture_*` threshold tie — this one has real headroom).

## What's still open

This debug shader verifies the rule in isolation at native resolution
(scale 1.0, matching `classify_debug.slang`'s precedent) — it does not yet
run at an actual upscale factor, and non-dither pixels are an unfiltered
placeholder rather than their own class's real reconstruction. Both are
T-020's job: fusing this rule with T-017 (class d) and T-018 (classes a/c)
into the single shipped mobile-lite pass, at the pass's real output
resolution.
