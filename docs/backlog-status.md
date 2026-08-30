# Backlog status — build session 2026-08-30

Tracks what this build session completed against `docs/backlog.md`, and — since the session ran in
a container with no GPU (`/dev/dri` absent) and no physical device — records exactly which Phase 0
tickets cannot be advanced further without external testing, and what that testing needs to be.

## Completed this session

| Ticket | What was built | Where |
|---|---|---|
| T-001 | Licensing posture for xBRZ/ScaleFX/SABR/Omniscale/HQx, sourced against the live libretro/slang-shaders repo | `docs/licensing.md` |
| T-002 | Cross-backend compile gate: stub `.slang` pass, glslang→SPIR-V→spirv-cross pipeline covering Vulkan/GL/GLES/HLSL/MSL, wired into CI | `tools/compile_gate/`, `.github/workflows/compile-gate.yml` |
| T-004 | Two-level classifier feasibility spike — **dither vs. AA-gradient separation passes (0.906, threshold 0.85)**, the ticket's explicit gate | `tools/classifier_spike/`, `tools/classifier_spike/spike_report.md` |
| T-005 | GLES floor decision: gather-only, no 3.0 fallback, sourced against real device GPU specs | `docs/gles-floor.md` |
| T-008 | Synthetic pattern generator: dither ramp, diagonal sweep (15-75° in 5° steps), glyph sheet, checkerboard-transparency, at 5 systems' native resolutions | `tools/patterns/generate_patterns.py`, `corpus/synthetic/` |
| T-009 / T-010 | Text legibility positive set (3 styles × 5) and false-positive negative set (3 categories × 5), both fully synthetic/redistributable | `tools/patterns/generate_text_sets.py`, `corpus/synthetic/text_positive/`, `corpus/synthetic/text_negative/` |
| T-012 | Perceptual A/B comparison harness — client-side, labeled/blind modes, JSON export | `tools/ab_compare/index.html` |
| T-014 | 256-entry 3×3 topology LUT, baked as RGBA8 texture + raw binary, symmetry/rotation invariants unit-tested | `tools/lut/generate_lut.py`, `tools/lut/lut_test.py`, `tools/lut/topology_lut.png` |

All of the above are independently re-runnable (`python3 tools/.../*.py`), have no dependency on a
GPU or physical device, and are committed with their generated output so CI/reviewers don't need to
regenerate to see results.

## Blocked on external testing

These backlog items cannot progress further inside this environment. Each needs something this
container structurally cannot provide (no `/dev/dri`, so no GPU/EGL/Vulkan context at all; no
network path to a specific physical device; no legal/community sourcing judgment call).

### T-003 — Headless golden-image regression harness
**Blocked on: a real or software GPU render backend.** The harness's job is producing actual
rendered frames from a compiled shader pass to diff against goldens — that requires an EGL/Vulkan
context, which this container doesn't have (`ls /dev/dri` → no such device; no `libEGL` driver
backend beyond the software `libGL.so.1`/Mesa stub already on the base image, which itself needs a
render node this container doesn't expose). **What unblocks it:** either (a) a session/runner with a
real GPU or a working software rasterizer path (Mesa llvmpipe over a surfaceless EGL platform can
render without `/dev/dri` on some hosts — worth trying first in an environment where sandboxing
allows kernel DRM/software-render fallback, since it would let this run in ordinary CI too), or (b)
deferring the actual render step to a GPU-equipped CI runner while keeping the comparator/diff logic
(which doesn't need a GPU) written now. Recommend building the PNG-diff/goldens-comparison half next
— that part is pure image math and can be written and tested without a renderer at all — and wiring
the render step in once a GPU-capable runner is available.

### T-006 — Reference handheld bring-up and measurement methodology
**Blocked on: physically possessing a Retroid Pocket-class Android device.** This is inherently not
something a cloud container can do. No workaround — this needs a person with the hardware.

### T-007 — Redistributable content corpus (real homebrew/PD game captures)
**Blocked on: sourcing and legally vetting specific homebrew/public-domain ROMs/captures.** Unlike
T-008/T-009/T-010 (which this session solved by generating everything synthetically, sidestepping
the redistribution question entirely), T-007 specifically wants real captured game frames across
NES/SMS, SNES/Genesis, and GB/GBC/GBA homebrew titles. That requires picking specific titles,
confirming each one's actual license/redistribution terms individually, and capturing frames from a
running emulator — a curation judgment call better made with the project owner's input on which
homebrew scene titles to use, not guessed at. The synthetic corpus already built covers the same four
content categories called for in §8 (flat-color sprite art via the glyph/checkerboard patterns,
dithered transparency, gradient-adjacent content via the AA half of the dither-ramp pattern, and the
diagonal sweep standing in for fast-scrolling-parallax edge content) well enough to unblock T-004 and
Phase 1 classifier work; T-007's real-game corpus remains open for whenever specific titles are
chosen.

### T-011 — Catalog existing-shader failure cases
**Blocked on: T-001's clean-room determination plus a render backend.** Running xBRZ/ScaleFX/SABR/
Omniscale/nearest-neighbour against the corpus to catalog their failure modes requires either (a)
actually executing those shaders (same GPU/render-backend blocker as T-003), or (b) reading their
GPLv2/GPLv3/LGPL source closely enough to describe failure modes without executing them, which
T-001 flags as exactly the kind of close reading that blurs into "derivation" for the three
copyleft implementations. Cleanest path once a render backend exists: run the two MIT-licensed
shaders (ScaleFX, Omniscale) directly, and characterize xBRZ/SABR/HQx failure modes from their own
published documentation/screenshots (already-public comparisons, not this project reading their
source) rather than by running project-controlled ports of GPL code.

## What "proceeding as far as possible" means from here

Everything in Phase 0 that's pure software — research, offline algorithm prototyping, compiler
tooling, synthetic content generation — is done. What's left in Phase 0 (T-003's render step, T-006,
T-007's real-game sourcing, T-011's shader execution) all need one of: a GPU-capable environment, a
physical handheld, or a human curation/licensing call. Phase 1 shader tickets (T-013 onward) are
next in the critical path (`T-001 → T-004 → T-016 → T-020 → ...`) and are also largely GPU-independent
until the point where actual rendered output needs verifying — worth continuing on the same basis
(write the `.slang` code and validate it through the T-002 compile gate, which only checks that it
*compiles*, not that it *looks right*) if the intent is to keep building blind of visual feedback, but
that tradeoff should be a deliberate call rather than a default, since a shader that compiles but has
never been seen rendered is a much larger blind spot than anything above.
