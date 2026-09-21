"""T-043 — analytical (no-hardware) lower bound on mobile-lite's B/px.

docs/requirements.md's own §6 ceiling table derives the mobile-lite budget as
"one output-res write (4 B) + amortized native-res source taps", and T-006's
own acceptance criteria explicitly need a *calculated* B/px to validate a
real measurement against (within +/-15%) — that calculated number doesn't
exist yet anywhere in this project, and T-006/T-021 (real handheld
measurement) remain blocked on hardware this environment doesn't have. This
script builds the calculated half now, so it's ready the moment T-006
unblocks, rather than starting from nothing then.

Method — cite-and-compute, not source parsing:
shaders/shaders_slang/argus/experimental/shaders/mobile-lite.slang's actual
read pattern was read by hand (see
KERNEL_RADIUS/FETCH_COUNT comments below for exact line references) and
encoded here as constants, the same level of rigor as tools/edge_reconstruct/
edge_reference.py's hand-ported CPU model — this is deliberately not a GLSL
static analyzer (out of scope, and this shader is simple enough not to need
one). Two numbers are reported, because they answer different questions:

1. **Fetch-instruction count** (`best_case_fetches`/`worst_case_fetches`) —
   directly countable from source, branch-dependent (isFlat/isDither/isStroke
   take the unconditional 25-tap classification kernel only; the edge branch
   adds up to 9 more), and this is what a real GPU's instruction/texture-unit
   issue count actually depends on, cache hits or not.
2. **Amortized unique-texel footprint** (`amortized_texels_per_output_px`) —
   an *ideal-cache* (compulsory-misses-only) model: for an NxN stencil kernel
   sampling a native-resolution source at an SxS output upscale, sliding the
   kernel across S consecutive output columns/rows only advances the source
   coordinate by 1 native texel, so S consecutive output pixels in a row
   touch only N+S-1 unique source texels in that dimension, not N*S —
   standard stencil-bandwidth amortization, assuming a texture cache that
   never evicts anything still in the sliding window. This is a **lower
   bound**: real hardware cache behavior (line granularity, eviction under
   contention, non-ideal reuse) can only push the real number up from here,
   never down. It is the closest thing to the requirements table's own
   "amortized native-res source taps" phrase that can be computed without a
   device.

All texture traffic here is against `Source`, bound RGBA8 (4 bytes/texel,
tools/render_harness/render_pass.py's own `make_texture`, matching how this
project's real .slangp presets declare it) — mobile-lite has no second
texture at runtime (T-014's LUT is embedded as a GLSL constant array in the
shipped pass, not sampled; see mobile-lite.slang's header comment and
tools/edge_reconstruct/report.md Finding 1), so there is exactly one texture
input to account for.

Usage: python3 tools/bandwidth_estimate/calculate_bpx.py
"""
import sys

# --- hand-verified against shaders/shaders_slang/argus/experimental/shaders/mobile-lite.slang ---
KERNEL_RADIUS_TEXELS = 5  # 5x5 classification kernel, lines 371-379 (dx,dy in -2..2), unconditional
EDGE_BRANCH_EXTRA_FETCHES = 9  # 8 topology-neighbor taps (line ~453-458) + 1 directional blend sample (~480/486)
BEST_CASE_FETCHES = KERNEL_RADIUS_TEXELS * KERNEL_RADIUS_TEXELS  # isFlat/isDither/isStroke: no extra taps
WORST_CASE_FETCHES = BEST_CASE_FETCHES + EDGE_BRANCH_EXTRA_FETCHES  # edge-reconstruction branch taken
# Edge-branch offsets are all within +/-1 of `coord` (both the 8-neighbor
# topology taps and the +/-1 directional blend sample), which is a strict
# subset of the 5x5 (+/-2) classification footprint — so the edge branch
# does not enlarge the *unique-texel* footprint, only the fetch-instruction
# count. Verified by inspection: OFFS entries and `off` are unit vectors.
EDGE_BRANCH_EXPANDS_FOOTPRINT = False

SOURCE_TEXEL_BYTES = 4  # RGBA8
OUTPUT_WRITE_BYTES = 4  # RGBA8 framebuffer write, per §6's ceiling table

# §6's own tier ceiling table (docs/requirements.md)
MOBILE_LITE_CEILING_BPX = 8.0

# T-018's own already-established "realistic" scale range for this tier
# (tools/edge_reconstruct/report.md's 2x-6x sweep), reused here rather than
# picking new numbers, so results are directly comparable.
SCALES = [2, 3, 4, 5, 6]


def amortized_texels_per_output_px(kernel_radius: int, scale: int) -> float:
    """Ideal sliding-window cache model, 1D amortization squared for 2D
    (uniform coverage assumption — this kernel and this upscale are both
    axis-aligned/separable in access pattern, so this is not an
    approximation of a non-separable case)."""
    unique_per_row = kernel_radius + scale - 1
    return (unique_per_row / scale) ** 2


def calculate(scale: int) -> dict:
    amortized_texels = amortized_texels_per_output_px(KERNEL_RADIUS_TEXELS, scale)
    read_bpx = amortized_texels * SOURCE_TEXEL_BYTES
    total_bpx = read_bpx + OUTPUT_WRITE_BYTES
    return {
        "scale": scale,
        "amortized_texels_per_output_px": amortized_texels,
        "amortized_read_bpx": read_bpx,
        "output_write_bpx": OUTPUT_WRITE_BYTES,
        "total_bpx_lower_bound": total_bpx,
        "within_ceiling": total_bpx <= MOBILE_LITE_CEILING_BPX,
    }


def main():
    print(f"mobile-lite fetch-instruction count per output pixel: "
          f"{BEST_CASE_FETCHES} (flat/dither/stroke) - {WORST_CASE_FETCHES} (edge branch)")
    print(f"§6 mobile-lite ceiling: {MOBILE_LITE_CEILING_BPX} B/px\n")

    rows = [calculate(s) for s in SCALES]
    print(f"{'scale':>6} | {'amortized texels/px':>20} | {'B/px (lower bound)':>19} | within ceiling?")
    for r in rows:
        verdict = "yes" if r["within_ceiling"] else "NO"
        print(f"{r['scale']:>5}x | {r['amortized_texels_per_output_px']:>20.2f} | "
              f"{r['total_bpx_lower_bound']:>19.2f} | {verdict}")

    write_report(rows)
    return 0


def write_report(rows: list):
    lines = [
        "# T-043 — analytical (no-hardware) B/px lower bound for mobile-lite",
        "",
        "Generated by `calculate_bpx.py`. See that file's module docstring for the full method and "
        "the exact `mobile-lite.slang` line references the constants below are drawn from — this is "
        "a hand-verified accounting of that shader's actual texture-read pattern, not output from a "
        "GLSL static analyzer.",
        "",
        f"**Fetch-instruction count per output pixel**: {BEST_CASE_FETCHES} "
        f"(isFlat/isDither/isStroke — the unconditional 5x5 classification kernel only) to "
        f"{WORST_CASE_FETCHES} (edge-reconstruction branch — adds up to 8 topology-neighbor taps + "
        "1 directional blend sample, all within the classification kernel's own +/-2-texel footprint, "
        "so they don't enlarge the unique-texel footprint below, only the instruction count).",
        "",
        "## Result",
        "",
        "| scale | amortized texels/output px (ideal cache) | B/px (lower bound) | "
        f"within §6's {MOBILE_LITE_CEILING_BPX} B/px ceiling? |",
        "|---:|---:|---:|---|",
    ]
    for r in rows:
        verdict = "yes" if r["within_ceiling"] else "**NO**"
        lines.append(
            f"| {r['scale']}x | {r['amortized_texels_per_output_px']:.2f} | "
            f"{r['total_bpx_lower_bound']:.2f} | {verdict} |"
        )

    lines += [
        "",
        "## Reading this honestly",
        "",
        "**This is a lower bound, not a prediction** — it assumes an ideal texture cache that never "
        "evicts anything still inside the kernel's sliding window (\"compulsory misses only\"), which "
        "no real GPU achieves. Real measured B/px on the reference handheld (T-006, still blocked on "
        "hardware) can only be equal to or higher than this number, never lower. That makes the result "
        "at every one of T-018's already-established realistic scales (2x-6x) worth flagging plainly: "
        "**even under this best-case assumption, mobile-lite's read bandwidth alone exceeds §6's "
        f"{MOBILE_LITE_CEILING_BPX} B/px ceiling at every tested scale**, by a wide and *growing* "
        "margin at lower scales (5x5 kernel amortization improves as scale increases, but never "
        "reaches the ~1 texel/px the ceiling's \"amortized native-res source taps\" language would "
        "need at 4 bytes/texel).",
        "",
        "This isn't a shader bug — it's the direct, structural consequence of what \"mobile-lite = 1 "
        "output-resolution pass\" (FR3) means: the full 5x5 classification kernel necessarily runs "
        "once per *output* pixel rather than once per *native* pixel, because there is no separate "
        "native-resolution pass to run it in once and reuse the result. `docs/requirements.md`'s own "
        "Phase 2 tier (T-023: \"native-res classification render target\") exists specifically to fix "
        "this — moving classification to a native-resolution pass so it runs once per native pixel, "
        "not once per output pixel — but that's a 2-pass tier, and T-023/T-024 aren't Phase 1 scope.",
        "",
        "**What this does and doesn't settle**: it doesn't replace T-006/T-021's real measurement — "
        "cache behavior on the actual reference handheld could still surprise in either direction "
        "(e.g. real GPUs also pay non-trivial fixed costs per texture-cache miss that this idealized "
        "model ignores entirely, which would push real numbers higher still, not lower). What it does "
        "settle is that **T-022's exit gate (\"≤ 8 B/px measured\") should not be assumed achievable "
        "as mobile-lite currently stands** without either hardware evidence to the contrary (texture "
        "caches occasionally do better than a naive sliding-window model on real tile-based mobile "
        "GPUs, so this is not certain to hold — just unlikely to reverse by 4x) or a design change. "
        "Recorded as new scope (T-043) rather than asserted as a T-022 pass/fail, since only real "
        "hardware can actually resolve it.",
    ]
    from pathlib import Path
    (Path(__file__).resolve().parent / "report.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    sys.exit(main())
