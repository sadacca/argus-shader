# T-020 — fuse classification + reconstruction into a single shipped pass

Resolves [T-020](../../docs/backlog.md#t-020--fuse-into-single-pass-mobile-lite-shader)
in `docs/backlog.md`. Fuses T-016's four-class classifier and T-017/T-018/
T-019's three per-class reconstruction rules into
`shaders/shaders_slang/argus/shaders/mobile-lite.slang`, the actual shipped
mobile-lite pass driven by `argus-mobile-lite.slangp`. See `verify_gpu.py`
(the fusion-specific check) and `tools/render_harness/goldens/argus-mobile-lite/`
(the committed regression goldens, now regenerated for the fused shader — see
Finding 1 for why they needed regenerating rather than just re-running).
Reproduce with:

```
python3 tools/fusion/verify_gpu.py
python3 tools/render_harness/run_harness.py       # regression check
python3 tools/compile_gate/compile_check.py shaders/shaders_slang/argus/shaders/mobile-lite.slang
```

## Result

```
Fusion parity (fused output vs. each class's own already-verified
  debug shader, on content dominated by that class):      PASS (0 px difference)
Compile gate (Vulkan/GL/GLES/D3D11-12/Metal):              PASS
Render-harness regression (60/60 content x preset tuples): PASS
1 pass, 1 output-resolution pass, zero intermediate RTs:   PASS (verified from .slangp: shaders=1)
Varyings ≤2 vec4, offsets computed in FS:                  PASS (1 varying, vec2 — see below)
Varying count ≤16 vec4 on Adreno 6xx:                      not device-verified (see below)
textureGather used where available:                        not attempted (see "What's still open")
```

## The fusion

Each block is a direct, unmodified port of its already-verified debug
shader's math — this ticket's job was combining four independently-correct
rules into one file without a transcription error, not re-deriving any of
them:

1. T-015/T-016's wide-kernel (5x5) scalar statistics and four-class
   classification (`classify_debug.slang`) run first, unconditionally, for
   every output pixel.
2. Class (b) (dither/checkerboard): T-019's blend-toward-mean rule
   (`dither_debug.slang`), gated by `ARGUS_DITHER_STRENGTH`.
3. Class (d) (thin strokes/glyphs): T-017's exact-source-color rule
   (`text_debug.slang`) — checked *before* the flat/edge branch since a
   stroke pixel can have high local variance and would otherwise misroute
   into edge reconstruction.
4. Classes (a)/(c) (hard edge / already-AA'd gradient): T-018's
   LUT-topology edge-directed blend (`edge_debug.slang`), gated by
   `ARGUS_EDGE_THRESHOLD`.
5. Class (a-flat) (flat, none of the above): unmodified source color.

`verify_gpu.py` checks this directly rather than re-deriving an independent
CPU model: for each corpus sample, it renders `classify_debug.slang` to get
each pixel's ground-truth label, then compares the fused shader's output
against whichever standalone debug shader owns that label's rule, pixel by
pixel, requiring exact match (`frac_over_tol < 0.01` at a 2/255 tolerance,
actual result 0.0000 everywhere) rather than re-verifying the underlying
math a second time — that's already each contributing ticket's job.

## Finding 1 — the render harness's own regression goldens were silently testing nothing of this ticket, because `scale0 = 1.0`

T-013's original skeleton `.slangp` set `scale0 = 1.0` — reasonable for
validating a passthrough pass end-to-end, since a passthrough has no
scale-dependent behavior to test. Running the harness against the fused
shader at that same `scale0` reported a clean `60/60 tuples matched their
golden` — but investigating *why* (the fused shader visibly changes 1.77%+
of pixels vs. nearest-neighbour on text content at 4x, see below) found the
goldens weren't actually exercising T-018's reconstruction at all:

`render_pass.py`'s `scale` argument sets output resolution as a literal
multiplier of source resolution. At `scale = 1.0`, output pixel centers land
exactly on source texel centers, so `edge_debug.slang`'s (and now the fused
shader's) sub-pixel fractional offset (`frac = srcCoordF - (coord + 0.5)`)
is exactly `0.0` for every pixel — not approximately, exactly, by
construction. `dist = dot(frac, normal)` is therefore always `0.0`, which
takes the `t = clamp(-dist*2.0, 0, 1) = 0` branch, which is `mix(centerColor,
neighbor, 0) = centerColor`. **The edge-reconstruction branch was a
mathematical no-op at `scale0 = 1.0`, independent of any of its logic being
right or wrong.** (Dither/checkerboard was *also* a no-op at the harness's
implicit default parameters before T-020 — see
`parse_pragma_parameter_defaults`'s docstring in `render_pass.py`, a related
gap this ticket also found and fixed, for a different reason: an empty
`params={}` silently tested `ARGUS_DITHER_STRENGTH = 0`, not its real
default of `1.0`.) Confirmed by direct measurement: rendering the fused
shader against the old `scale0 = 1.0` goldens gave 0 pixels of difference
across the entire corpus, including on `diagonal_sweep` content specifically
constructed to exercise edge reconstruction.

This is the same class of gap as the GLES-300-vs-310 mismatch and the CI
globstar bug documented elsewhere in this project: tooling that *looks*
green while silently not checking the thing it claims to check.

**Fix**: `argus-mobile-lite.slangp`'s `scale0` is now `4.0` — the middle of
the realistic 2x-6x range T-018's own report characterizes, chosen for the
same reason that report used 4x as one of its five tested points. This has
no effect on real RetroArch playback (`scale_type0 = viewport` means the
runtime always renders to the actual output viewport regardless of
`scale0`'s value; `scale0` only matters to this offline harness, which has
no notion of a real viewport and reads the field literally). All 60 goldens
were regenerated at `scale0 = 4.0` and spot-checked visually (see below)
before committing — per this project's own stated discipline, golden
updates are reviewable diffs in the commit, never written to paper over an
unreviewed change.

## Visual spot-check (manual, this session)

Rendered several corpus samples at 4x and diffed against a plain
nearest-neighbour 4x upscale of the same source:

| content | changed px vs. nearest-neighbour | notes |
|---|---|---|
| `diagonal_sweep/nes_256x240` | 0.19% | only the steepest (near-vertical) tooth picks up a blend; shallow teeth are untouched — matches T-018 Finding 2's compass-snapping limitation exactly, not a new bug |
| `dither_ramp/genesis_320x224` | 0.04% | small edge-adjacent effect only; dither region itself is untouched at `ARGUS_DITHER_STRENGTH = 1.0` (full preservation), as designed |
| `text_positive/outlined_00` | 1.77% | glyph interiors untouched (T-017 protection); changes are at true, mostly axis-aligned glyph edges |
| `checkerboard_transparency/smw_256x224` | 0.00% | content classified entirely as dither/flat here; exact match to nearest-neighbour, as FR2 requires |

No unexpected blurring, no blend bleeding into protected stroke pixels, no
change on pure-flat content. This is consistent with each rule's own
already-verified behavior; fusing them did not introduce new artifacts.

## Verifying the acceptance boxes without physical Adreno hardware

`docs/backlog.md`'s "verified on Adreno 6xx" box can't be checked from this
environment (no physical device — same limitation as T-006/T-021/T-018
Finding 1 elsewhere in this project). What *can* be verified here is the
varying count itself, which is a compile-time fact independent of GPU
vendor: `spirv-cross`'s GLES 310 output for the vertex stage shows exactly
one `layout(location = 0) out vec2 vTexCoord` crossing into the fragment
stage — no texel-size or per-tap-offset varyings; every neighbor offset is
computed in the fragment shader from `global.SourceSize` (a uniform) plus
the base coordinate, exactly as required. One `vec2` varying is trivially
within any GLES 3.1 budget (the spec's guaranteed floor is far above the
16-vec4 ceiling this ticket's box asks about) — checked in `docs/backlog.md`
on that basis, with a note that it isn't hardware-verified.

## What's still open

- **`textureGather` is not used** (every neighbor tap is an individual
  `texelFetch`, matching what each contributing debug shader already
  verified). This is a real, tracked performance optimization — T-005's
  device matrix is gather-only with no GLES 3.0 fallback needed, so nothing
  blocks adopting it — but it changes the fetch pattern in a way that would
  need its own from-scratch verification against a CPU reference, and this
  project's actual bandwidth/frame-time numbers (T-021, T-022) are blocked
  on real handheld hardware (T-006) regardless of whether this shader uses
  `textureGather` or not. Left unattempted here to keep this ticket's scope
  to "fuse the four already-correct rules," not "also optimize the fetch
  pattern," per the same reasoning T-018's own report gives for not chasing
  the Omniscale gap inside that ticket.
- **T-014's topology LUT is embedded as a generated `const vec3[256]` array**,
  not sampled from its baked texture as originally designed — carried
  forward unchanged from `edge_debug.slang` (T-018 Finding 1: a real,
  reproducible Mesa/llvmpipe miscompilation with a dynamically-indexed
  `texelFetch` on a second sampler). This matters more here than in the
  debug shader, since this is the actual shipped pass: **re-verifying the
  texture-sampling path on real GPU hardware, and switching back to it if
  safe there, is the natural next step**, not assumed to be either safe or
  unsafe from this environment's llvmpipe-specific bug.
- **T-041** (class-(d) classifier separability — text/glyph strokes vs.
  fur/hair/architecture/weapon-outline content, 80.8% measured false-positive
  rate per T-017's report) is unchanged by this ticket. Misrouted pixels
  still fall back to T-018's edge reconstruction rather than T-017's
  exact-preservation rule; T-017's report already argues this is a safe
  fallback, not a crash or a worse-than-nearest-neighbour regression.
- **T-018's honest non-win against Omniscale** (wins 1 of 5 tested scales)
  is unchanged by fusion — this ticket didn't touch the reconstruction math,
  only combined it with the other three rules.
- **T-040's legacy `.glslp`/`.glsl` pack** does not yet have this ticket's
  logic ported — its acceptance box for "each tier's algorithm ported to
  legacy syntax as its slang counterpart lands (T-020 mobile-lite first)"
  remains unchecked. Still tracked as open, not a blocker for shipping the
  slang pack.
- **T-022** (Phase 1 exit validation — perceptual comparison, bandwidth,
  frame time, false-positive rate against a real threshold) has not been
  run. This ticket's fusion-correctness and no-regression checks are
  necessary but not sufficient for T-022's own acceptance criteria.
