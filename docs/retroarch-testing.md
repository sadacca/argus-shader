# Testing argus-mobile-lite side-by-side in RetroArch

Everything needed to load `mobile-lite.slang` in a real RetroArch install already exists and passes
this project's own compile gate on all five backends (Vulkan, GL, GLES, D3D11/12, Metal) — nothing
here is blocked on further shader work. What follows is just the install/comparison steps, since
nothing in this repo currently documents them.

## 1. Install the preset

Copy this repo's `shaders/shaders_slang/argus/` directory into RetroArch's own shader directory —
where that is depends on platform:

- Linux: `~/.config/retroarch/shaders/`
- Windows: `<RetroArch install dir>\shaders\`
- Android: `/storage/emulated/0/Android/data/com.retroarch/files/shaders/` (or wherever RetroArch's
  own Settings → Directory → Video Shader is pointed)

The result should be a `shaders/argus/argus-mobile-lite.slangp` (plus its `shaders/mobile-lite.slang`)
under RetroArch's shader root.

## 2. Load it

In-game: **Quick Menu → Shaders → Load → argus/argus-mobile-lite.slangp**. Or set it as a default so
it's applied automatically: **Quick Menu → Shaders → Save → Save Global Preset** (applies to every
core) or **Save Core/Content/Content Directory Preset** for a narrower scope.

If nothing changes visually, confirm the shader driver is actually `slang` (**Settings → Drivers →
Video → slang**) — the legacy `.glsl` pack under `shaders_glsl/argus/` is for RetroArch installs that
predate or don't support the slang pipeline, and needs the `gl`/`glcore` driver instead, loaded from
Quick Menu → Shaders the same way.

## 3. A/B against SABR, ScaleFX, xBRZ

These are standard community shaders already shipped with RetroArch — no need to fetch or vendor
anything to test with them:

**Settings → Shaders → Auto-Shaders enable → Online Updater → Update Shaders** (or **Update Slang
Shaders**) pulls RetroArch's own bundled shader library, which includes each of these under
`shaders/edge-smoothing/<name>/`. Load the same way as step 2: **Quick Menu → Shaders → Load →
edge-smoothing/sabr/sabr.slangp** (or `scalefx/scalefx.slangp`, `xbrz/2xbrz-linear.slangp`).

RetroArch doesn't have a true split-screen A/B view — the practical way to compare is to load one
preset, take a screenshot (**F8** by default, or the Screenshot hotkey), switch to the next preset via
Quick Menu → Shaders → Load, screenshot again, and compare stills. `tools/ab_compare/index.html`
(T-012, already in this repo) can load a matched pair of screenshots side by side for exactly this.

## 4. What this project's own numeric comparison already shows

Before spending time on manual A/B in RetroArch, worth knowing what `tools/eval_metric/
rpg_text_eval.py`'s ground-truth comparison already found (see its `rpg_text_report.md`): on IoU
against a known-correct supersampled render, **xBRZ scores highest on both tested scenes, SABR and
ScaleFX both beat argus-mobile-lite, and argus-mobile-lite is roughly tied with plain
nearest-neighbour** — not the result this project's earlier, more limited comparisons suggested.
Manual RetroArch testing is still worth doing (this metric doesn't capture everything — motion,
real game content, frame time), but go in expecting to see xBRZ/SABR/ScaleFX look at least as good on
static text, not expecting argus-mobile-lite to visibly win.
