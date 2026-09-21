# Testing in RetroArch

**There is currently no shipped preset to install.** `argus-mobile-lite` — the only preset this
project has ever built — was retired from general use (`docs/backlog.md` P-3, 2026-09-20): it
measures worse than nearest-neighbour on real smooth content (`tools/gold_eval/report.md`) and real
RetroArch testing found it "slow and nearly unplayable... no benefit whatsoever to smoothing" next
to xBRZ. It's kept under `shaders/shaders_slang/argus/experimental/` and
`shaders/shaders_glsl/argus/experimental/` purely as a named baseline the eval harness scores future
candidates against — **do not install it expecting a usable result.** This file will describe real
install/load steps again once Track F (`docs/backlog.md`) produces a preset worth installing.

## What's still true and reusable

**Settings → Shaders → Auto-Shaders enable → Online Updater → Update Shaders** (or **Update Slang
Shaders**) pulls RetroArch's own bundled shader library, which already includes SABR, ScaleFX, and
xBRZ under `shaders/edge-smoothing/<name>/` — no need to fetch or vendor anything to compare them
directly: **Quick Menu → Shaders → Load → edge-smoothing/xbrz/2xbrz-linear.slangp** (or
`sabr/sabr.slangp`, `scalefx/scalefx.slangp`).

RetroArch doesn't have a true split-screen A/B view — the practical way to compare is to load one
preset, take a screenshot (**F8** by default, or the Screenshot hotkey), switch to the next preset via
Quick Menu → Shaders → Load, screenshot again, and compare stills. `tools/ab_compare/index.html`
(this repo) can load a matched pair of screenshots side by side for exactly this.

## What this project's own numeric comparison already shows

Before spending time on manual A/B in RetroArch, worth knowing what `tools/gold_eval/report.md` and
`tools/eval_metric/rpg_text_report.md` already found: on IoU against known-correct ground truth,
**xBRZ scores highest of every tested candidate, SABR and ScaleFX both clear a real margin over
nearest-neighbour, and the retired argus-mobile-lite prototype is roughly tied with plain
nearest-neighbour** on content with a genuine smooth source. This is the gap Track F
(`docs/backlog.md`) exists to close.

## Loading the retired prototype anyway (for eval-harness comparison only)

If you specifically want to reproduce this project's own baseline numbers by eye rather than trust
the metric: copy `shaders/shaders_slang/argus/experimental/` into RetroArch's shader directory
(platform-dependent — Linux: `~/.config/retroarch/shaders/`; Windows:
`<RetroArch install dir>\shaders\`; Android: wherever Settings → Directory → Video Shader points),
then **Quick Menu → Shaders → Load → experimental/argus-mobile-lite.slangp**. Confirm the shader
driver is `slang` (**Settings → Drivers → Video → slang**) first — the legacy `.glsl` pack under
`shaders_glsl/argus/experimental/` needs the `gl`/`glcore` driver instead, loaded the same way.
