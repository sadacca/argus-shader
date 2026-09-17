# Vendored third-party comparison shaders — not this project's code

`scalefx/` in this directory is an unmodified, verbatim copy of six files from
[`libretro/slang-shaders`'s `edge-smoothing/scalefx/`](https://github.com/libretro/slang-shaders/tree/master/edge-smoothing/scalefx)
(`scalefx.slangp` and `shaders/scalefx-pass{0..4}.slang`), plus the shared
`stock.slang` passthrough it references as `shader0`, fetched 2026-09-17.
It is MIT-licensed (Sp00kyFox, 2016; the full license text is embedded in
each pass file's own header, per its terms) — `docs/licensing.md`'s T-001
determination clears ScaleFX for direct reading, adaptation, and execution
("**ScaleFX — go.**").

**This is vendored for T-011's comparison set but is not currently
executable through this project's render harness.** ScaleFX is a 6-pass
filter chain with named cross-pass texture aliasing (`scalefx-pass2.slang`
reads `scalefx_pass0`'s output by its `.slangp` alias name; `scalefx-pass4.slang`
reads both `Source` and a separate `refpass` alias) and float
intermediate framebuffers. `tools/render_harness/`'s `render_pass.py` and
`run_harness.py` are both explicitly single-pass only (see each file's own
docstring) — there is no multi-pass filter-chain sequencer in this project
yet (the same category of work Phase 2's T-023/T-024 will eventually need
for this project's own 2-pass Mobile/mid tier). Building one correctly
enough to trust a comparison metric against it is real, unverified
infrastructure work, not something to improvise inline for a comparison
run — see `tools/comparison/report.md` for what this blocks and what it
would take to unblock.

Nothing in this directory was copied or adapted into this project's own
code. Retain the MIT notice embedded in each file if this directory is
ever redistributed.

**xBRZ, SABR, and HQx are deliberately not vendored here.** Per
`docs/licensing.md`, all three carry copyleft licenses (GPLv3, GPLv2+, and
LGPL2.1 respectively) with no permissive subset covering direct execution.
T-011's own backlog entry already treats even *running* their unmodified
code for comparison purposes as gated on a human licensing-scope decision
("accepting GPL/LGPL obligations on specifically those comparison runs"),
not merely deriving from them — T-018 already established this position
for SABR specifically (see `tools/edge_reconstruct/reference_shaders/NOTICE.md`);
this directory follows the same, already-established position for all
three rather than making a new call unilaterally.
