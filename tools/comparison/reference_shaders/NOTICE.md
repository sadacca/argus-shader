# Vendored third-party comparison shaders — not this project's code

`scalefx/` in this directory is an unmodified, verbatim copy of six files from
[`libretro/slang-shaders`'s `edge-smoothing/scalefx/`](https://github.com/libretro/slang-shaders/tree/master/edge-smoothing/scalefx)
(`scalefx.slangp` and `shaders/scalefx-pass{0..4}.slang`), plus the shared
`stock.slang` passthrough it references as `shader0`, fetched 2026-09-17.
It is MIT-licensed (Sp00kyFox, 2016; the full license text is embedded in
each pass file's own header, per its terms) — `docs/licensing.md`'s T-001
determination clears ScaleFX for direct reading, adaptation, and execution
("**ScaleFX — go.**").

**Update 2026-09-19: now executable.** `tools/render_harness/render_multipass.py` is a real multi-pass
filter-chain sequencer (handles the named cross-pass aliasing and float intermediate framebuffers
described below), built once SABR/xBRZ also needed multi-pass execution rather than one improvised for
ScaleFX alone. Building it found that the `stock.slang` copy alongside this directory (referenced by
`scalefx.slangp`'s unmodified `shader0 = ../../stock.slang`) was vendored one directory level too
shallow for that reference to resolve — the preset was never actually executed before, so this was
never caught. Fixed by placing an identical copy at `tools/comparison/stock.slang` (the depth the
unmodified preset actually expects), not by editing the vendored preset's own path. See
`docs/backlog-status.md`'s 2026-09-19 update for the full list of bugs the sequencer surfaced (this
one plus two more affecting SABR/xBRZ/HQx specifically) and `tools/comparison/generate_rpg_baselines.py`
for how ScaleFX is now actually run. ScaleFX is a 6-pass filter chain with named cross-pass texture
aliasing (`scalefx-pass2.slang` reads `scalefx_pass0`'s output by its `.slangp` alias name;
`scalefx-pass4.slang` reads both `Source` and a separate `refpass` alias) and float intermediate
framebuffers — all now handled.

Nothing in this directory was copied or adapted into this project's own
code. Retain the MIT notice embedded in each file if this directory is
ever redistributed.

**xBRZ, SABR, and HQx are still deliberately not vendored here** (source stays out of this repo's own
git history even now that they're runnable) **but SABR and xBRZ now run**, per the user's direct
2026-09-19 go-ahead — see `docs/backlog-status.md`'s 2026-09-19 update for the correction to this
file's earlier "gated on a licensing-scope decision" framing, which had drifted into characterizing
this project's own conservative choice as a pending user decision that was never actually put to
them. Their source is fetched to a scratch location outside this repo for comparison runs; only
rendered *output* is committed (`tools/comparison/renders/` is `.gitignore`d as regeneratable
regardless). HQx remains unrun here — not on licensing now, but a real unresolved rendering bug (see
`docs/backlog-status.md`), and it's also the most legally marginal of the three per `docs/licensing.md`
("conditional; default to no-go"), so it wasn't worth chasing further once the other two were unblocked.
