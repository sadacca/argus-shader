# Backlog status

Rewritten 2026-09-20 for the v0.3 pivot. The detailed session-by-session build log (2026-08-30
through 2026-09-19, T-001 through T-047) is preserved in this repo's git history — every ticket's
commit is tagged in its message — and isn't duplicated here. This file states where the project
actually stands right now. See `docs/requirements.md` for the current spec and `docs/backlog.md`
for the reusable/retired ticket breakdown.

## The pivot, in one paragraph

The v0.2 direction optimized for preserving the source's blocky pixel grid and deliberate dithering,
with text specially routed to a nearest-neighbour "protection" path. Two independent, real signals
showed that was the wrong goal: this project's own gold-standard eval (`tools/gold_eval/report.md`)
found the shipped prototype tied or lost to doing nothing at all on content with a genuine smooth
source, while xBRZ/SABR/ScaleFX all cleared a 9-13 point margin over nearest-neighbour on the same
content — and real RetroArch testing by the project owner independently reported the shader as
"slow and nearly unplayable" with "no benefit whatsoever to smoothing" next to xBRZ. `docs/
requirements.md` v0.3 reverses the goal in response: reconstruct smooth, vector-faithful shapes
uniformly across all content, with text/glyph fidelity as the explicit differentiator, instead of
protecting blockiness.

## What's reusable right now

The evaluation and build infrastructure doesn't encode a position on the aesthetic question — it
measures against ground truth — so it all survives unchanged. Full list with paths: `docs/
backlog.md`'s "Reusable" table. Highlights:

- `tools/gold_eval/` is now the primary quality gate (it's what caught the problem).
- `tools/render_harness/`, `tools/compile_gate/`, and CI (`.github/workflows/compile-gate.yml`)
  continue to gate every commit.
- `tools/comparison/` already runs real xBRZ/SABR/ScaleFX/Omniscale/nearest-neighbour baselines
  through the same harness — the new algorithm gets compared against them the same way.

## What's retired

The four-class region classifier, the dither-preservation rule, the text-protection rule, and the
shipped `mobile-lite.slang` fusing them are retired — not deleted, kept in git history — because they
implement the reversed goal. Full list with rationale: `docs/backlog.md`'s "Retired" table.

One concrete engineering finding from that work is worth carrying forward even though the shader
itself is retired: inspecting `mobile-lite.slang`'s compiled GLES output found its classification
kernel writes 25 taps into local arrays in one loop, then reads those arrays back across five
*separate* subsequent loops (mean, variance, checkerboard, luma-bin popcount, foreground
comparisons) — a well-known GPU register-spilling hazard invisible to software-rasterizer testing
(the only kind available in this environment; no physical ARM device). Whatever replaces it should
be checked for this pattern in compiled output, not just reviewed at the source level.

## Genuinely blocked (unchanged by the pivot)

- **Physical ARM reference handheld** — needed for real frame-time/bandwidth measurement. No
  substitute found; software rasterization (Mesa llvmpipe/Lavapipe) doesn't model real GPU register
  allocation or bandwidth behavior, which is exactly what the finding above depends on confirming.
- **Real-game redistributable content corpus** — a public repo can't ship captured frames from
  commercial ROMs. Current corpus is synthetic plus generated RPG-style content
  (`tools/comparison/generate_rpg_text.py`); homebrew/public-domain captures remain unaddressed.

## What's next

See `docs/backlog.md`'s "What's next" section — redesigning the core reconstruction algorithm
against `tools/gold_eval`'s vector-regime metric is the current critical path.
