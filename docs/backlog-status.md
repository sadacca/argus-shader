# Backlog status — build session 2026-08-30

Tracks what this build session completed against `docs/backlog.md`, and — since the session ran in
a container with no GPU (`/dev/dri` absent) and no physical device — records exactly which Phase 0
tickets cannot be advanced further without external testing, and what that testing needs to be.

## Update — 2026-09-17

Two changes to the picture above:

1. **This environment now has a working render backend — T-003 is unblocked.** Re-probed rather than
   assumed: `/dev/dri` is still absent, but `EGL_EXT_platform_device` (headless, surfaceless — no X11/
   Wayland/DRM needed) successfully initializes Mesa, and a real GLES 3.2 context renders
   (`GL_RENDERER: llvmpipe (LLVM 20.1.2, 256 bits)`). A parallel probe against `libvulkan.so.1` gets a
   `VK_SUCCESS` instance and enumerates one physical device (`llvmpipe`, `VK_PHYSICAL_DEVICE_TYPE_CPU`)
   — Lavapipe, Mesa's software Vulkan implementation. This is exactly the fallback path this document
   previously flagged as "worth trying first" (§T-003 above). **Important nuance: this is Mesa's CPU
   software rasterizer (llvmpipe/Lavapipe), not hardware GPU acceleration** — the host does appear to
   expose real GPU infrastructure to this WSL2 environment (`/dev/dxg` present, `libd3d12.so`/
   `libdxcore.so` under `/usr/lib/wsl/lib`, and a host driver DLL visible at
   `/mnt/c/Drivers/video/*/Graphics/libEGL.dll`), but the headless device-platform path this probe used
   only enumerated the software renderer, not that hardware. That distinction matters for two different
   tickets:
   - **T-003 (golden-image regression harness) is unblocked as designed.** It needs correct,
     bit-reproducible rendered frames to diff against goldens — a deterministic software rasterizer is
     actually a *better* fit for that than hardware, which can introduce vendor-specific rounding
     differences. Nothing about T-003's acceptance criteria requires real GPU hardware.
   - **T-006 / T-021 (bandwidth and frame-time measurement on reference mobile hardware) remain
     blocked.** llvmpipe/Lavapipe numbers are not representative of Adreno/Mali tile-based mobile GPU
     bandwidth behavior in any way — this backend answers "does it render correctly," not "is it fast
     enough on target hardware." Do not substitute this environment's timings for T-006/T-021.

   Practically: build the T-003 render step now, alongside the comparator logic already recommended
   below. `glslangValidator`/`spirv-cross` (used by T-002's compile gate) are not currently installed in
   this interactive session (only in the CI runner, via the workflow's own `apt-get install`) — they
   need to be installed here too before the render step can consume T-002's cross-compiled output.

2. **New scope: a legacy `.glslp`/`.glsl` preset pack is required alongside the `.slang` pack.**
   Until now this project targeted RetroArch's modern slang pipeline only (`.slangp`/`.slang`,
   Vulkan-semantics GLSL, cross-compiled per-backend via T-002's SPIR-V/spirv-cross gate). That pipeline
   does **not** produce a legacy-format shader as a side effect — RetroArch's older GLSL shader driver
   (`.glslp` preset + single-file `.glsl` with `#if defined(VERTEX)`/`#elif defined(FRAGMENT)`
   conditional compilation, `COMPAT_*` macros, non-Vulkan-semantics implicit uniform bindings) uses a
   structurally different file format from what spirv-cross's GL/GLES backend targets emit for the
   slang path, even though the underlying reconstruction math can be shared conceptually. This is now
   tracked as **T-040** in `docs/backlog.md`, requires its own root preset skeleton mirroring T-013, and
   needs the compile gate extended to validate the legacy format too (`glslangValidator` can check it
   directly with `-D VERTEX`/`-D FRAGMENT` defines against non-Vulkan GLSL semantics — confirmed
   feasible in principle against a real example file from `libretro/glsl-shaders`, not yet wired in).

## Update — 2026-09-17 (continued: render harness and legacy gate built)

Picking up directly from the update above in the same session:

- **T-003 is built**, not just unblocked. `tools/render_harness/` renders a `.slang` pass through the
  literal GLES cross-compile T-002's gate already validates (glslangValidator → SPIR-V →
  `spirv-cross --es`), against a real headless GLES 3.0 context (`egl_context.py`, ctypes against
  `libEGL.so.1` via `EGL_EXT_platform_device` — PyOpenGL's own EGL bindings don't cover the
  device-enumeration extensions this path needs, so context creation is hand-rolled and GL calls go
  through PyOpenGL once the context is current). `glslangValidator`/`spirv-cross` are now installed in
  this interactive session (confirmed on PATH, not just in the CI runner as previously noted) and
  `PyOpenGL`/`numpy`/`Pillow` installed cleanly via `pip3 --user --break-system-packages` — no sudo,
  no apt, needed for any of this. Verified end to end: the stub pass and the mobile-lite skeleton both
  render as byte-identical passthroughs of their source image, twice-rendered frames hash-identical
  (determinism), and deliberately corrupting a golden is correctly caught and reported with a
  mismatched-pixel-count/percentage and max-delta message. 55 goldens seeded for the
  `argus-mobile-lite` preset against the entire synthetic corpus (`tools/render_harness/goldens/`).
  **Not done:** actually rendering through GL-desktop, Vulkan, D3D11/12, or Metal — only GLES is
  executed; see T-003's backlog entry for exactly what's missing from each. Wired into CI as a second
  job (`render-harness`) in `.github/workflows/compile-gate.yml`.

- **T-040's compile-gate box is done**: `tools/compile_gate/compile_check_legacy.py` compiles every
  shipped legacy `.glsl` file's vertex and fragment stages directly (no SPIR-V step — the legacy
  driver isn't Vulkan-semantics GLSL) against GLES 300 (the actual T-005 target), desktop GLSL 150 and
  120, and GLES 100 (checked only because the file's own `COMPAT_*` macros claim `#if __VERSION__ >=
  130` support for it — not a real target, and labeled as such after an earlier draft of this script
  mislabeled it as "the T-005 floor," which it is not; T-005 floors this project at GLES 3.1+, not
  GLES 2.0). **Caught a real bug in the T-040 skeleton while building this**: the shared `TEX0`
  varying was declared before any GLSL ES default float precision existed, which GLSL ES's fragment
  stage requires before the first unqualified float declaration — glslangValidator rejected it
  outright. Fixed by moving `precision mediump float` before the shared declaration rather than
  leaving it inside the `FRAGMENT`-only branch (see the shader file's own comment, and the earlier
  header comment noting a *different*, already-fixed ordering issue in the same area — this is a
  second instance of the same class of bug, which suggests the general pattern is worth double-
  checking again once real reconstruction code adds more declarations to this file).

- **Found and fixed a second, unrelated bug while wiring T-040 into CI**: the existing
  `.github/workflows/compile-gate.yml` step that compiles shipped `.slang` passes used
  `shaders/**/*.slang` with only `shopt -s nullglob` set, not `globstar` — without `globstar`, bash's
  `**` behaves as an ordinary single-level `*`, so it silently matched nothing against the actual
  three-levels-deep `shaders/shaders_slang/argus/shaders/*.slang` path and the step has been printing
  "no shipped .slang passes yet" instead of actually gating shipped shaders since T-013 first landed.
  Fixed by adding `globstar`; confirmed locally that the corrected glob now matches. The equivalent
  legacy-`.glsl` CI step was added with `globstar` from the start.

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
**Status: unblocked as of 2026-09-17 — see the Update section above.** A surfaceless
`EGL_EXT_platform_device` context against Mesa llvmpipe (GLES 3.2, confirmed by direct probe) and a
Lavapipe software Vulkan device (confirmed via `vkCreateInstance`/`vkEnumeratePhysicalDevices`) are
both reachable without `/dev/dri`. Neither is hardware-accelerated, but T-003's acceptance criteria
(byte-identical output across two runs, per-tuple pixel-delta diffing against committed goldens) call
for correctness/determinism, not mobile-representative performance, so a software rasterizer is a
legitimate implementation, not a workaround-with-caveats. Next step: build the render step (feed
T-002's cross-compiled backend output through the appropriate context — GL/GLES via EGL, Vulkan via
the Lavapipe ICD) and the PNG-diff/goldens-comparison logic together; both are buildable now.

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
**Status: partially unblocked as of 2026-09-17.** The render-backend half of this ticket's blocker is
resolved (see the Update section above and T-003) — ScaleFX and Omniscale (both MIT, cleared for
direct execution per `docs/licensing.md` §2) can now actually be run against the corpus through the
same EGL/Vulkan software-rasterizer path. **Still blocked:** xBRZ/SABR/HQx remain no-go/conditional
for *execution* of project-controlled ports under T-001's clean-room determination — that half needs
either a licensing-scope decision (accepting GPL/LGPL obligations on specifically those comparison
runs) or continuing to characterize their failure modes from published documentation/screenshots
rather than by running project-controlled code, as already recommended. T-007's real-game corpus is
also still needed for full coverage; the synthetic corpus can unblock a first pass on ScaleFX/Omniscale
now.

## What "proceeding as far as possible" means from here

Everything in Phase 0 that's pure software — research, offline algorithm prototyping, compiler
tooling, synthetic content generation — is done. As of 2026-09-17, **T-003 is actually built**, not
just unblocked (see Update above): a shader pass can be rendered through a real GLES context and
checked against a committed golden in one command (`python3 tools/render_harness/run_harness.py`).
T-013 (slang skeleton) and T-040 (legacy skeleton) both exist as passthrough passes, both pass their
respective compile gates, and both are seeded with goldens. Phase 1 shader work no longer has to
proceed blind of visual feedback by default, and now doesn't have to build its own render harness
first either — that part is done. What's still genuinely stuck (T-006, T-007's real-game sourcing, the
copyleft half of T-011) needs a physical handheld or a human curation/licensing call — nothing left in
that set is a tooling gap.

**Next up on the critical path** (`T-001 → T-004 → T-016 → T-020 → T-023 → T-025 → T-033`): T-001 and
T-004 are already done (see "Completed this session" above and the README), so **T-016 (region
classifier, FR2)** is the next unstarted ticket — it consumes T-004's spike output and T-014's baked
LUT (also already done) to actually classify pixels into edge/dither/AA/flat regions, which is the
first piece of real reconstruction logic rather than skeleton/passthrough work. Recommended sequencing
per ticket, now that the harness exists: implement against the passthrough skeleton, run
`tools/compile_gate/compile_check.py` for portability, then `tools/render_harness/run_harness.py
--update-goldens` once the rendered output is visually confirmed correct (goldens are reviewable diffs
in the commit, per T-003's third acceptance box — never update them to paper over an unreviewed
change). T-040's legacy pack should get the same treatment in parallel as each tier lands, not written
after the fact from finished slang passes.

**Still open on T-003 itself**, tracked as unchecked in its backlog entry rather than left implicit:
GL-desktop execution (same EGL device, different API binding — small lift, not yet wired), a headless
Vulkan render path (distinct boilerplate from EGL/GLES, not started), and D3D11/12/Metal remain
compile-only since no runtime for either exists on this platform.
