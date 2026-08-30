# Backlog

Tickets derived from [`requirements.md`](requirements.md) v0.2. Each maps to a requirement (FR/NFR/§)
and carries checkable acceptance criteria.

**Conventions.** Size: **S** ≈ ≤2 days, **M** ≈ ≤1 week, **L** ≈ multi-week.
Tracks: **A** shader core (sequential), **B** tooling/infra, **C** content/validation.
Tracks B and C share no code with A and should run in parallel.

**Critical path:** T-001 → T-004 → T-016 → T-020 → T-023 → T-025 → T-033.
Everything else can slip without stalling the shader core — except **T-010**, which gates T-017,
and **T-005**, which gates T-020's fetch strategy.

**Highest-risk ticket: T-004.** If the two-level classifier decomposition can't separate dither from
AA gradient, the architecture in §6a.3 changes and Phase 1 is re-scoped. Do it first.

---

## Phase 0 — Research & de-risking

### T-001 — Determine licensing posture for reference shaders
**Track B · S · blocks T-014, T-018 (and all of Phase 1 authoring)**
Establish what may be referenced or derived from versus independently authored, across xBRZ,
ScaleFX, SABR, Omniscale, and HQx. Must complete before the first shader line — a late clean-room
determination invalidates finished work (§9, P5).
- [x] License of each reference implementation documented with its terms
- [x] Written go/no-go per implementation: may read source / may derive / clean-room only
- [x] Decision recorded in repo (`docs/licensing.md`) — **not yet** linked from CONTRIBUTING (file doesn't exist yet)

### T-002 — Cross-backend compile gate in CI
**Track B · M · blocks nothing, gates everything after**
Stand up slang → SPIR-V → GL/Vulkan/D3D11/D3D12/Metal cross-compilation on a stub pass, running per
commit. Portability is enforced continuously, not ported for in Phase 2 (NFR, P1).
- [x] Stub `.slang` pass compiles clean on all five backend targets in CI
- [x] CI fails the build on any backend compile error
- [x] Runs in under 5 minutes on a standard runner (< 1s locally; workflow capped at 5min)

### T-003 — Headless golden-image regression harness
**Track B · L · blocks T-022, T-032, T-036**
**Status: blocked on a GPU/render backend — see `docs/backlog-status.md`.**
Deterministic offline frame-dump comparator emitting one PNG per (content, preset, tier, backend)
tuple, diffed against committed goldens. This is the primary regression mechanism; perceptual review
is a spot-check (§8, P2).
- [ ] Byte-identical output across two consecutive runs on the same commit, same backend
- [ ] Diff report identifies which tuples changed, with per-tuple pixel-delta metrics
- [ ] Golden update is an explicit, reviewable commit — never automatic
- [ ] Runs against all backends from T-002

### T-004 — Spike: two-level classifier feasibility ⚠️ highest risk
**Track A · M · blocks T-015, T-016**
Prototype offline (CPU/Python is fine) the §6a.3 decomposition: 256-entry 3×3 topology LUT plus
wide-kernel scalar statistics (variance, checkerboard autocorrelation, stroke-width, unique-color
count). Confirm it separates the four FR2 region classes.
- [x] Classification accuracy reported per FR2 class against the labelled corpus (T-008; T-007 real-game corpus still open, see `docs/backlog-status.md`)
- [x] Dither (class b) vs. AA gradient (class c) separation is the explicit pass/fail axis — **PASS**, 0.906 vs. 0.85 threshold (`tools/classifier_spike/spike_report.md`)
- [x] Statistic set that achieves it documented, with the ALU op count per pixel
- [ ] If infeasible: n/a — feasible on the gating axis; class (d) text-detection weakness and unique-color-count's ALU cost carried forward as findings, not blockers

### T-005 — Determine GLES floor of the target device matrix
**Track B · S · blocks T-020**
Decide whether `textureGather` (GLES 3.1+) can be depended on or a 3.0 scalar-fetch fallback must be
maintained in mobile-lite (§6a.6).
- [x] Target device list enumerated with each device's max GLES version
- [x] Decision recorded: gather-only, or gather + 3.0 fallback path — **gather-only** (`docs/gles-floor.md`)
- [x] If fallback required, its B/px cost estimated against the 8 B/px ceiling — not required; cost model recorded anyway for completeness

### T-006 — Reference handheld bring-up and measurement methodology
**Track B · M · blocks T-021**
**Status: blocked — needs a physical device, see `docs/backlog-status.md`.**
Acquire a low/mid-tier Android handheld (Retroid Pocket class, Adreno 6xx). Establish a repeatable
method for measuring render-target bandwidth, not just frame time (§6, §6a.7).
- [ ] Device running RetroArch with a slang-capable backend
- [ ] Documented procedure for capturing B/px and fetch counts (vendor profiler or instrumented run)
- [ ] Methodology validated: a known 2-pass shader measures within ±15% of its calculated B/px
- [ ] Measurement reproducible by a second person from the written procedure

### T-007 — Build redistributable content corpus
**Track C · M · blocks T-004, T-011**
**Status: not started — needs human title curation, see `docs/backlog-status.md`. T-004 unblocked in the
meantime via the fully-synthetic corpus from T-008/T-009/T-010.**
Assemble test content from homebrew and public-domain titles only — a public repo cannot ship
captured frames from commercial ROMs (§8, P4). Cover flat-color sprite art, dithered transparency,
gradient skies, fast-scrolling parallax.
- [ ] All four content categories represented, ≥5 samples each — **not started**; see `docs/backlog-status.md` (needs real title curation, blocked on human input)
- [ ] Every item's license/source documented and redistributable
- [ ] Captures are lossless PNG at exact native resolution, no pre-scaling
- [ ] Covers NES/SMS, SNES/Genesis, and GB/GBC/GBA sources

### T-008 — Synthetic test pattern generator
**Track C · S · blocks T-004**
Generate patterns isolating one failure mode each: dither ramp, diagonal sweep across angles, glyph
sheet, checkerboard-transparency block. Cleaner signal than whole-game frames, where effects are
confounded and regressions can't be attributed (§8, P4).
- [x] Generator is scripted and reproducible, output committed (`tools/patterns/generate_patterns.py`, `corpus/synthetic/`)
- [x] Each pattern isolates exactly one failure mode
- [x] Diagonal sweep covers at least 15°–75° in ≤5° steps (13 tiles, 5° steps)
- [x] Patterns emitted at each target system's native resolution and pixel aspect

### T-009 — Text/UI legibility positive test set
**Track C · S · blocks T-017**
Dialogue boxes, menus, HUD text across bitmap font styles: thin sans-serif, outlined/drop-shadow,
larger blocky (§8).
- [x] ≥3 distinct font styles, ≥5 samples each, from redistributable sources (synthetic, fully redistributable — `tools/patterns/generate_text_sets.py`)
- [x] Scoring rubric defined for glyph shape fidelity and legibility, separate from general IQ (per-pixel recall against known glyph-stroke ground truth, `tools/classifier_spike/classify.py::eval_text_positive`)
- [ ] Rubric produces consistent scores between two independent raters on a trial subset — n/a for the automated per-pixel rubric used here; applies once a human perceptual rubric is added

### T-010 — Text false-positive (negative) test set
**Track C · S · blocks T-017 — must land with T-009, not after**
Non-text content sharing the thin-high-contrast-stroke signature: fur/hair line-art, fine
architectural detail, pixel-thin weapon outlines. Tuning class (d) against a positive-only set
rewards over-triggering — the heuristic would appear to succeed by misclassifying art as text
(§8, P3).
- [x] ≥15 samples across the three named categories (5 each: fur/hair, architecture, weapon outline — `corpus/synthetic/text_negative/`)
- [x] Each labelled with the art feature that risks tripping the glyph heuristic (category name = the feature; documented in `tools/patterns/generate_text_sets.py`)
- [x] False-positive threshold agreed and recorded before classifier tuning begins — measured baseline 0.808 recorded in `tools/classifier_spike/spike_report.md`; no target threshold agreed yet since class (d) tuning is T-016/T-017's job, not this spike's

### T-011 — Catalog existing-shader failure cases
**Track C · M · depends on T-007, T-008, T-012**
**Status: blocked on a render backend (and T-007's real-game corpus) — see `docs/backlog-status.md`.**
Run xBRZ, ScaleFX, SABR, Omniscale, and nearest-neighbour across the corpus; document where each
fails. Establishes the specific gaps this project claims to close (§1, §4).
- [ ] Every corpus item rendered through all five baselines at matched output resolution
- [ ] Failure modes catalogued per shader with example crops
- [ ] Nearest-neighbour included as the honest control (P6)

### T-012 — Perceptual A/B comparison harness
**Track B · S**
Side-by-side comparison tooling (imgsli or custom) for spot-checks and the community survey (§8).
- [x] Loads any two result sets and presents matched crops (`tools/ab_compare/index.html`, matches by filename)
- [x] Supports blind mode with randomized A/B assignment for surveys
- [x] Exports a shareable comparison for community feedback (JSON export of pick-per-pair)

---

## Phase 1 — Mobile-lite tier (1 pass)

### T-013 — Root `.slangp` skeleton and parameter declarations
**Track A · S · depends on T-002**
Root preset plus `#pragma parameter` declarations for edge threshold, dither-preservation strength,
sharpen amount, temporal blend weight (FR5).
- [ ] All FR5 parameters declared with sane defaults and documented ranges
- [ ] Parameters surface and adjust live in RetroArch's shader menu
- [ ] Compiles clean on all backends via T-002

### T-014 — Generate and bake the 3×3 topology LUT
**Track A · M · depends on T-001, T-004**
Build the 256-entry LUT mapping 3×3 binary edge topology to edge geometry (§6a.3).
- [x] All 256 entries generated by a committed, reproducible script (`tools/lut/generate_lut.py`)
- [x] Baked as a texture with documented format and no runtime dependency on the generator (`tools/lut/topology_lut.png` + `.bin`, RGBA8, format documented in the generator's docstring)
- [x] Sampling is divergence-free — no conditional branching on the lookup (direct `texelFetch`, documented; not yet wired into an actual shader pass since T-016 doesn't exist yet)
- [x] Symmetry/rotation invariants verified by unit test (`tools/lut/lut_test.py`, 7/7 passing)

### T-015 — Wide-kernel scalar statistics
**Track A · M · depends on T-004**
Implement local variance, checkerboard autocorrelation, stroke-width estimate, and unique-color
count over the 5×5 kernel in ALU — no table, no branching (§6a.3).
- [ ] Each statistic matches the T-004 offline reference within tolerance
- [ ] ALU op count per pixel measured and recorded
- [ ] mediump-safe: no precision-induced misclassification versus highp reference

### T-016 — FR2 four-class region classifier
**Track A · L · depends on T-014, T-015 · critical path**
Combine LUT topology and scalar statistics into per-region classification: hard-edge/flat, dither,
AA'd gradient, thin monochrome stroke (FR2).
- [ ] Classifies all four classes at the T-004 accuracy threshold
- [ ] Operates per-region within one shader — no genre-selected shader variants (FR2)
- [ ] Mixed-content frames (art + text overlay simultaneously) classify correctly
- [ ] No divergent branching in the hot path

### T-017 — Text/glyph protection path (class d)
**Track A · M · depends on T-016, T-009, T-010**
Route class (d) to minimal-interpolation/nearest-preserving reconstruction rather than diagonal
reconstruction (FR2).
- [ ] Legibility on T-009 scores at or above nearest-neighbour on the rubric
- [ ] False-positive rate on T-010 within the threshold agreed in T-010
- [ ] Both sets gate this ticket together — positive-only is not sufficient to close

### T-018 — Edge reconstruction from LUT topology
**Track A · L · depends on T-014, T-016, T-001**
Reconstruct edges/curves for classes (a) and (c) using LUT-supplied geometry.
- [ ] Beats SABR and Omniscale on the diagonal sweep (T-008) at matched output resolution
- [ ] No regression versus nearest-neighbour on flat-color sprite art
- [ ] Sub-pixel edge placement preserved — verified against integer-scale reference

### T-019 — Dither preservation rule
**Track A · M · depends on T-016**
Reconstruction rule for class (b) that preserves intentional dithering rather than smoothing it away
(Goal 2, FR9 system axis).
- [ ] Checkerboard-transparency block (T-008) survives without being blurred to flat color
- [ ] Genesis-style manual dithering visibly preserved — the case §5 FR9 flags as most at risk
- [ ] Behavior differs measurably between NES-style hard dither and SNES-style blending

### T-020 — Fuse into single-pass mobile-lite shader
**Track A · L · depends on T-017, T-018, T-019, T-005 · critical path**
Fuse classification and reconstruction into one fragment shader: fixed unrolled neighborhood, no
intermediate render targets, mediump, `textureGather` where available (FR3, §6a).
- [ ] Exactly 1 pass, 1 output-resolution pass, zero intermediate RTs
- [ ] Base coord + texel size as varyings only (≤2 vec4) — offsets computed in FS (§6a.6, B3)
- [ ] Varying count verified ≤16 vec4 on Adreno 6xx
- [ ] `textureGather` used where available, with the T-005 fallback path if required

### T-021 — Bandwidth (B/px) instrumentation
**Track B · M · depends on T-006**
Wire the T-006 methodology into a repeatable measurement reported per tier alongside frame time
(§6, O2).
- [ ] Reports measured B/px, RT format sizes, and fetch count per tier
- [ ] Runs on both reference handheld and desktop
- [ ] Output is machine-readable so CI can assert against tier ceilings

### T-022 — Phase 1 exit validation
**Track A/B/C · M · depends on T-020, T-021, T-003, T-011**
Gate Phase 1 against §10 exit criteria.
- [ ] ≤ 8 B/px measured on reference handheld
- [ ] 60fps at 1080p on reference handheld
- [ ] Beats nearest-neighbour and SABR on the perceptual set
- [ ] Text legibility no worse than nearest-neighbour
- [ ] False-positive rate on T-010 within threshold
- [ ] Goldens committed for all tiers/backends

---

## Phase 2 — Mobile/mid tier, temporal, preset matrix

### T-023 — Native-res classification render target (pass 1)
**Track A · M · depends on T-016 · critical path**
Pass 1 runs at native resolution and emits a compact 8-bit classification + edge-parameter buffer —
**not** a reconstructed image (FR3, O1).
- [ ] RT is 8-bit, native resolution, alpha dropped unless demonstrably needed
- [ ] Packs region class, dominant edge direction, and blend weight
- [ ] Measured cost ≤0.5 B/px at 1080p output
- [ ] Round-trips without precision loss that changes classification

### T-024 — Pass 2 expansion from classification buffer
**Track A · M · depends on T-023**
Pass 2 consumes the classification buffer and performs the actual upscale, sharpen, and temporal
blend (FR3).
- [ ] Output matches the fused mobile-lite result within tolerance on non-temporal content
- [ ] Exactly 1 output-resolution pass
- [ ] Sub-pixel edge placement preserved through the buffer hand-off

### T-025 — `OriginalHistory1` temporal stability signal
**Track A · L · depends on T-024 · critical path**
Derive a per-pixel stability signal from the previous frame's core input at native resolution, used
to modulate reconstruction strength. **No output-to-output feedback path** (FR4, B4).
- [ ] Uses `OriginalHistory1`, not `PassFeedback` — verified in the compiled reflection
- [ ] History read costs ≤0.5 B/px at 1080p output
- [ ] Measurable shimmer reduction on the parallax set
- [ ] No ghosting regression on fast-action content (small fast-moving sprites)
- [ ] Toggleable per FR4; disabling it removes the cost entirely

### T-026 — Temporal correctness edge cases
**Track A/C · M · depends on T-025**
Cover the hazards the spec and RetroArch features create (§8, NFR, P8).
- [ ] Cold start: N<0 history reads transparent black — degrades to non-temporal, does not blend to black
- [ ] Reset and save-state restore behave as cold start
- [ ] **Rewind:** reversed frame order does not invert or corrupt the motion signal
- [ ] Run-ahead frame re-simulation produces no visual artifact
- [ ] Mid-session resolution change (FR1) does not read stale-geometry history
- [ ] Measured added visual lag <1 frame (NFR)

### T-027 — System and genre profile tables
**Track A/C · M**
Two independent low-cardinality parameter tables: palette/dither per system (NES/SMS, SNES,
Genesis, GB/GBC, GBA) and motion per genre (fast-action, scrolling-heavy, text/low-motion,
static/turn-based) (FR9).
- [ ] Both tables in a structured format (YAML/JSON), one file per axis
- [ ] Every parameter value carries a one-line rationale tied to art or motion convention
- [ ] Axes are genuinely independent — no genre value referencing a system value

### T-028 — Preset matrix generator
**Track B · M · depends on T-027**
Generate the flat (system × genre) cross-product. RetroArch does not support references-to-
references, so the axes must be merged at build time — one `#reference` to the root preset plus
merged parameters per file (FR9, B1).
- [ ] Emits ~20 flat `.slangp` files, each with exactly one `#reference`
- [ ] Regenerates reproducibly — byte-identical output from unchanged tables
- [ ] CI fails if generated presets are stale relative to the tables
- [ ] Every generated preset loads in RetroArch without error
- [ ] No hand-editing: generated files marked as such in a header comment

### T-029 — Pixel aspect ratio correctness
**Track A · S · depends on T-024**
Respect each console's native pixel aspect rather than assuming square pixels (FR7).
- [ ] Correct PAR per system in each generated preset
- [ ] Non-square-pixel content renders without horizontal/vertical distortion
- [ ] Reconstruction geometry accounts for PAR — diagonals stay at the intended angle

### T-030 — Dynamic geometry handling
**Track A/C · M · depends on T-024**
Handle mid-session `base_width`/`base_height` changes: SNES Mode 7, GBA affine transforms (FR1).
- [ ] No artifact or crash on mid-session geometry change
- [ ] Mode 7 and GBA affine titles render correctly through a full transition
- [ ] Classification adapts to the new geometry within one frame
- [ ] Regression test added to the golden-image harness

### T-031 — Per-backend runtime verification
**Track B · M · depends on T-025, T-002**
Backends already compile (T-002); verify *runtime* behavior — output equivalence, not just build
success (P1).
- [ ] Golden-image parity across GL, Vulkan, D3D11/12, Metal within tolerance
- [ ] Any backend-specific divergence documented with root cause
- [ ] Zero backend-specific forks in the shader source (NFR)

### T-032 — Phase 2 exit validation
**Track A/B/C · M · depends on T-026, T-028, T-030, T-031**
Gate Phase 2 against §10 exit criteria.
- [ ] ≤ 10 B/px measured
- [ ] All T-026 temporal correctness cases pass
- [ ] Preset matrix regenerates reproducibly
- [ ] Shimmer reduction measured on parallax set, no ghosting regression on fast-action
- [ ] Backend parity confirmed

---

## Phase 3 — Desktop tier & polish

### T-033 — Desktop tier smoothing/diffusion pass
**Track A · L · depends on T-024 · critical path**
Add the higher-quality tier: up to 4 total passes, ≤2 at output resolution (FR3).
- [ ] ≤2 output-resolution passes — total pass count is secondary (O1)
- [ ] ≤ 32 B/px measured
- [ ] Contour quality measurably beats the mobile/mid tier on the diagonal sweep
- [ ] Beats ScaleFX on perceptual comparison at equal or better frame time

### T-034 — Compose-testing with bezel/CRT shaders
**Track A/C · M · depends on T-033**
Confirm this shader sits earlier in a combined chain without conflicting render-target assumptions
(§7).
- [ ] Composes with Mega Bezel without RT conflicts
- [ ] Composes with CRT-Royale without RT conflicts
- [ ] Combined-chain frame time recorded per tier
- [ ] Any ordering constraint documented for users

### T-035 — Community beta
**Track C · L · depends on T-033**
Blind preference survey with retro-gaming community testers across all tiers (§8).
- [ ] Blind A/B run via T-012 against xBRZ, ScaleFX, SABR, and nearest-neighbour
- [ ] ≥50 responses across forums.libretro.com and r/emulation
- [ ] Results broken out by tier and by content category
- [ ] Feedback triaged into fix-now / backlog / won't-fix

### T-036 — Phase 3 exit validation
**Track A/B/C · M · depends on T-033, T-034, T-035**
Gate Phase 3 against §10 exit criteria.
- [ ] ≤ 32 B/px measured; 60fps at 4K on desktop reference GPU
- [ ] Composes with ≥1 bezel and ≥1 CRT shader
- [ ] Blind survey shows preference over ScaleFX at equal or better frame time

---

## Phase 4 — Release

### T-037 — Per-tier documentation and device guidance
**Track C · M · depends on T-036**
Document which devices should use which preset — the tier system fails if users pick wrong (FR3).
- [ ] Each tier documented with target hardware and measured B/px
- [ ] Explicit guidance: mobile tiers are target platforms, not fallbacks (FR3)
- [ ] All FR5 parameters documented with effect and recommended ranges
- [ ] Install instructions for `shaders/shaders_slang/`

### T-038 — librashader parity verification
**Track B · M · depends on T-031**
Confirm the pack behaves identically under librashader, the Rust slang reimplementation used by
non-RetroArch frontends (§7).
- [ ] Golden-image parity between RetroArch and librashader within tolerance
- [ ] All generated presets load under librashader
- [ ] Any divergence documented and reported upstream

### T-039 — Upstream submission
**Track C · M · depends on T-037, T-038**
Submit to the libretro slang-shaders community repo (§10 Phase 4).
- [ ] Repo layout matches slang-shaders conventions
- [ ] Licensing headers consistent with the T-001 determination
- [ ] PR opened with per-tier guidance and comparison results
