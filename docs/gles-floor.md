# GLES Floor of the Target Device Matrix

**Resolves:** the GLES floor of the target device matrix (see [`docs/backlog.md`](backlog.md), "Reusable"
table). Decides whether a future mobile-tier reconstruction pass can depend on `textureGather`
(GLES 3.1+ core, per `docs/review-notes.md` O3) or must carry a GLES 3.0 scalar-fetch fallback path.
This decision is independent of the v0.3 pivot (`docs/requirements.md`) — it's a device-capability
fact, not tied to the retired dither/text-protection architecture that originally motivated it.

## 1. Target device matrix

Devices named in `README.md`'s target hardware line ("Retroid/Anbernic/Steam Deck class") plus the
current budget end of that same product family, since it's the segment most likely to fall below a
floor set from flagship specs alone.

| Device (or class) | SoC | GPU | Max GLES | Source |
|---|---|---|---|---|
| Retroid Pocket 5 | Snapdragon 865 | Adreno 650 @ 587MHz | 3.2 | [Adreno 650 vs 660 vs 619 — Notebookcheck](https://www.notebookcheck.net/Adreno-650-vs-Adreno-660-vs-Adreno-619_9971_10603_10584.247598.0.html) |
| Retroid Pocket 4 Pro | Snapdragon 8+ Gen 1 | Adreno 730-class | 3.2 | [Retroid Pocket 4 Pro issue thread, ppsspp#20480](https://github.com/hrydgard/ppsspp/issues/20480) (device confirmed running the GLES renderer path) |
| Anbernic RG557 | Dimensity 8300 | Mali-G615 MC6 @ 1.4GHz | 3.2 | [Anbernic/Retroid comparison — fun-esports.com](https://fun-esports.com/en/blogs/consoles-portables-retro/anbernic-or-retroid-pocket) |
| Anbernic RG35XX / RG35XX Pro/H/SP (budget tier, high unit volume) | Allwinner H700 | Mali-G31 MP2 | 3.2 (+ Vulkan 1.1) | ["Mali-G31 MP2... supports OpenGL ES 3.2 and Vulkan 1.1"](https://retrohandhelds.gg/anbernic-rg35xx-pro-setup-guide/), corroborated across [Anbernic's own RG35XX H product page](https://anbernic.com/products/rg35xx-h) |
| Adreno 618/619 (common in mid-tier Android handhelds broadly, not one specific SKU) | — | Adreno 618/619 | 3.2 | [Adreno 650 vs 618 vs 660 — Notebookcheck](https://www.notebookcheck.net/Adreno-650-vs-Adreno-618-vs-Adreno-660_9971_9900_10603.247598.0.html) |
| Steam Deck (LCD/OLED) | Custom AMD (Van Gogh / Phoenix) | RDNA2 iGPU | N/A — desktop GL 4.6 / Vulkan 1.3, not GLES at all | RetroArch on Steam Deck runs its GL or Vulkan desktop driver path, never the GLES driver; not part of this floor determination |

**Reading the table.** Every Android handheld checked — flagship (Retroid Pocket 4 Pro/5) down to
the cheapest currently-shipping Anbernic SKU (RG35XX family, Mali-G31 MP2) — reports GLES 3.2.
GLES 3.2 is a strict superset of 3.1 and mandates `textureGather` as core functionality (not an
extension), matching the citation already in docs/review-notes.md's sources list ([textureGather,
OpenGL ES 3.1 reference](https://registry.khronos.org/OpenGL-Refpages/es3.1/html/textureGather.xhtml)).
Steam Deck never touches the GLES driver path at all, so it doesn't constrain this floor either way.

## 2. Decision

**Gather-only. No GLES 3.0 scalar-fetch fallback path in the mobile-lite tier.**

Every device in the stated target class — including the budget end of the Anbernic line, which is
the highest-volume/lowest-spec hardware realistically running this shader — reports GLES 3.2,
comfortably above the GLES 3.1 floor `textureGather` requires. There is no device in §1 that would
need the fallback; building and maintaining a second scalar-fetch code path for a case with zero
observed target devices would cost real complexity (two texture-fetch strategies to keep in sync
through every future edit to T-020) for no coverage benefit.

**What this decision does not cover.** Genuinely legacy or off-target hardware — e.g., first-generation
Retroid Pocket / Pocket 2 (older, weaker Adreno models), ultra-budget handhelds built on Mali-400-class
or PowerVR SGX-class GPUs (GLES 2.0/3.0 only), or Android TV boxes/emulation on very old tablets — is
out of scope per `README.md`'s own framing ("mobile is a target platform, not a degraded mode" implies
a defined target, not universal Android support). If a future ticket wants to extend support to that
tier, it should reopen this decision with its own device data rather than silently degrading the
gather-only assumption made here.

## 3. Fallback cost estimate (not required, recorded for completeness)

T-005's acceptance criteria ask for the fallback's B/px cost "if required." It isn't required per §2,
but for the record: a GLES 3.0 scalar-fetch path replaces each `textureGather` (4 texels/instruction)
with 4 discrete `texture()` calls covering the same taps. This does not change render-target
*bandwidth* (B/px) at all — it's a fetch-count/instruction-count cost (more ALU/texture-unit
instructions per pixel for the same data volume moved), not a bytes-moved cost. It would not affect
the mobile-lite tier's 8 B/px ceiling (docs/requirements.md §6) either way; the cost is exclusively in
frame time on GLES-3.0-only hardware, which per §1 does not exist in the target matrix.

## 4. Revisit trigger

Re-open this decision if: (a) the target device list in `README.md`/`requirements.md` §2 is
explicitly widened to include pre-2019 or sub-$30 hardware, or (b) T-021's bandwidth instrumentation,
once run on real reference hardware (T-006, currently blocked — see `docs/backlog-status.md`), finds a
device in the stated class that doesn't actually expose `textureGather` despite reporting GLES 3.2
(a driver bug rather than a spec gap, but worth guarding against empirically once real hardware is in
the loop).
