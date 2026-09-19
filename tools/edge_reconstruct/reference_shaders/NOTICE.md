# Vendored third-party comparison shaders — not this project's code

`omniscale.slang` in this directory is an unmodified, verbatim copy of
[`libretro/slang-shaders`'s `edge-smoothing/omniscale/shaders/omniscale.slang`](https://github.com/libretro/slang-shaders/blob/master/edge-smoothing/omniscale/shaders/omniscale.slang),
fetched 2026-09-17. It is MIT-licensed (Lior Halphon, 2015-2016; the full
license text is embedded in the file's own header, per its terms) —
`docs/licensing.md`'s T-001 determination clears Omniscale for direct
reading, adaptation, and execution ("**Omniscale — go.** MIT in both its
origin... and its slang port").

**This file is here strictly as an external comparison baseline for
T-018's `verify_gpu.py`** (rendered through `tools/render_harness/` exactly
as-is, alongside this project's own `edge_debug.slang`, to measure T-018's
"beats Omniscale on the diagonal sweep" acceptance criterion against real
rendered output rather than an assumption). It is not part of any shipped
preset (`shaders/shaders_slang/` / `shaders/shaders_glsl/`), was not read
before designing `edge_reference.py`'s reconstruction rule (that design was
fixed first, based only on the generic, published "3x3 topology → edge
geometry" concept `tools/lut/generate_lut.py` already documents as
unpatentable and common to many pixel-art scalers — see `docs/licensing.md`
§4), and nothing in it was copied or adapted into this project's own code.
Retain the MIT notice embedded in the file itself if this directory is ever
redistributed.

**SABR was deliberately not vendored here.** Unlike Omniscale, SABR is
GPLv2-or-later with no permissive subset (`docs/licensing.md`), and T-011's
own backlog entry already treats even *running* SABR's unmodified code for
comparison purposes as gated on a human licensing-scope decision ("accepting
GPL/LGPL obligations on specifically those comparison runs"), not just
derivation. T-018 follows that same, already-established project position
rather than making a new call unilaterally — see `report.md`'s "What's
still open" for what unblocking this would need.
