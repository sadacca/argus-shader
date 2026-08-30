# Licensing Posture for Reference Shaders

**Resolves:** [T-001](backlog.md#t-001--determine-licensing-posture-for-reference-shaders) — "Determine
licensing posture for reference shaders," Phase 0, Track B. Blocks T-014, T-018, and all of Phase 1
shader authoring per the backlog and requirements §9/P5: this determination must exist before the
first shader line is written, because a clean-room finding made after code exists would invalidate
that work rather than merely gate future work.

**Scope.** For each of the five reference implementations named in requirements.md §4 (xBRZ, ScaleFX,
SABR, Omniscale, HQx), this document records the actual license as found in the relevant repository,
what that license permits with respect to this project, and a go/no-go verdict. All claims below are
sourced against the live repositories, cloned/fetched during this research (libretro/slang-shaders at
commit `4812a82f6c9a11cc8b5a7447040a98c9fc80c00e`); none are asserted from memory.

**Project license status.** As of this writing, argus-shader has not declared its own license (no
`LICENSE` file in the repo root, no statement in `README.md` or `requirements.md`). The verdicts below
are written conservatively — assuming the project wants the option of a permissive (MIT/BSD-style)
license, which is both the common convention for standalone `.slangp` preset packs and the safer
default, since narrowing later (permissive → copyleft) is always possible but widening
(copyleft → permissive) after code is written is not. Declaring the project license is a prerequisite
for CONTRIBUTING.md, which does not yet exist; this document should be linked from it once created, as
T-001's acceptance criteria specify.

## 1. Findings by implementation

| Implementation | License | Source | Verdict | Notes |
|---|---|---|---|---|
| **xBRZ** | GPLv3, with a narrow special exception | [snes9x `filter/xbrz.h`](https://github.com/snes9xgit/snes9x/blob/master/filter/xbrz.h) header (Zenju copyright notice); original project at [sourceforge.net/projects/xbrz](https://sourceforge.net/projects/xbrz/) | **Clean-room only** | The libretro/slang-shaders GLSL/slang ports (`edge-smoothing/xbrz/shaders/2xbrz.slang`, `.../xbrz-freescale.slang`) are not independently licensed — they embed the identical GPLv3 "HqMAME project" notice verbatim (see below). Reading/porting them carries the same GPL exposure as the original C++. |
| **ScaleFX** | MIT | [libretro/slang-shaders `edge-smoothing/scalefx/shaders/scalefx-pass1.slang`](https://github.com/libretro/slang-shaders/blob/master/edge-smoothing/scalefx/shaders/scalefx-pass1.slang), header credits Sp00kyFox, 2016, embedded in every pass file | **May derive** | Standard MIT text (copy/modify/sublicense permitted, notice must be retained). Compatible with any project license, permissive included. |
| **SABR** | GPLv2-or-later | [libretro/slang-shaders `edge-smoothing/sabr/shaders/sabr-v3.0.slang`](https://github.com/libretro/slang-shaders/blob/master/edge-smoothing/sabr/shaders/sabr-v3.0.slang), header credits Joshua Street | **Clean-room only** | Whole-file GPLv2(+) header, no exception. File also states it incorporates "portions... from Hyllian's 5xBR v3.7c shader," so the GPL binds the combined work regardless of Hyllian's own code's licensing elsewhere. |
| **Omniscale** | MIT | [libretro/slang-shaders `edge-smoothing/omniscale/shaders/omniscale.slang`](https://github.com/libretro/slang-shaders/blob/master/edge-smoothing/omniscale/shaders/omniscale.slang), header credits Lior Halphon, 2015-2016; original implementation ships in [LIJI32/SameBoy](https://github.com/LIJI32/SameBoy) (also MIT, see repo `LICENSE`) | **May derive** | Same MIT terms as ScaleFX. Author (Lior Halphon) is also SameBoy's maintainer; both the standalone and slang-ported code carry MIT headers, no divergence found between them. |
| **HQx** (hq2x/hq3x/hq4x) | LGPL 2.1 (or later) | [libretro/slang-shaders `edge-smoothing/hqx/shaders/hq2x.slang`](https://github.com/libretro/slang-shaders/blob/master/edge-smoothing/hqx/shaders/hq2x.slang), header credits Maxim Stepin (2003, original author), Cameron Zemek (2010), Jules Blok (2014) | **Clean-room recommended** | LGPL is weaker copyleft than GPL, but the "linking" carve-out LGPL relies on is written for compiled/dynamically-linked libraries and doesn't map cleanly onto shader source copied directly into another project's `.slang` files. Directly porting this code would put those specific files under LGPL 2.1 obligations, which is inconsistent with a project that hasn't ruled out an eventual uniform permissive license. See §3 for the conditional case where this is acceptable. |

**On "the overall repo license" question.** libretro/slang-shaders carries **no repository-wide
`LICENSE` file and no license statement in its `README.md`** (both checked directly against the
current default branch). Licensing in that repository is per-file/per-author, exactly as each
shader's own header states — confirmed by directly reading the shipped shader files above rather than
inferring a blanket libretro license. Any future reference into that repo for a different algorithm
must repeat this per-file check; there is no shortcut via a top-level grant.

## 2. Go/no-go per implementation

**xBRZ — no-go for direct derivation.** The algorithm's canonical implementation is GPLv3, and the
special exception Zenju grants is a named allowlist (MAME, FreeFileSync, Snes9x, ePSXe) — it does not
extend to arbitrary third-party projects, argus-shader included. Critically, the libretro slang-shaders
ports commonly cited as "the RetroArch xBRZ shader" are not a clean permissive rewrite: they embed the
same GPLv3 notice inline, copied from the HqMAME project, alongside separately-MIT-licensed code from
Hyllian for the vertex/texel-mapping portion. Reading either the original C++ or the slang port to
understand xBRZ's rule-based pattern-matching approach is fine — algorithms and ideas aren't
copyrightable — but no code text, structure, or LUT/rule tables may be copied or transliterated from
either source. Any xBRZ-equivalent behavior in this project must be independently authored against a
prose/public description of the technique (e.g., Zenju's own public write-ups of the rule set), not the
source.

**ScaleFX — go.** MIT end to end, with the license text embedded directly in every pass file this
project would reference. Direct porting/adaptation is permitted; retain Sp00kyFox's copyright notice
in any file derived from it, per the standard MIT condition.

**SABR — no-go for direct derivation.** The shader is GPLv2-or-later with no linking exception, and it
explicitly incorporates portions of Hyllian's 5xBR algorithm into the same GPL-covered file. There is
no permissive subset to carve out — the whole file is offered under GPL terms. As with xBRZ, this
project may study SABR's approach (its use of a wide-kernel pass to resolve interpolation ambiguity at
pixel junctions) from published descriptions or by reading the code for comprehension, but must not
copy or adapt the shader source itself if the project intends to remain permissively licensed.

**Omniscale — go.** MIT in both its origin (SameBoy) and its slang port, with consistent headers in
both. No caveats found. Direct porting/adaptation is permitted, with copyright notice retained.

**HQx — conditional; default to no-go.** LGPL 2.1 is a meaningfully weaker copyleft than xBRZ/SABR's
GPL, and if this project were willing to ship the specific HQx-derived shader file(s) under LGPL 2.1
terms (a mixed-license repository, which is legally straightforward — just not uniform), direct porting
would be legitimate. But the LGPL's core permission — link a compiled library into a differently
licensed program without that program inheriting LGPL — presumes a build-time/runtime linking boundary
that a `.slang` source file copied wholesale into a filter chain does not have. Absent an explicit
decision to accept LGPL obligations on the HQx-derived pass(es), treat HQx the same as xBRZ/SABR:
understand the algorithm (the 3×3-neighborhood binary-comparison → lookup-table structure that
requirements §6a.3 explicitly builds on) from public descriptions — e.g., the algorithm writeups
already cited in review-notes.md's technical discussion — rather than by porting `hq2x.slang`,
`hq3x.slang`, or `hq4x.slang` directly.

## 3. What this means for Phase 1 shader authoring

Two of five reference implementations (**ScaleFX, Omniscale**) are unencumbered MIT and may be read,
ported, and adapted directly, with attribution retained in derived files. Three (**xBRZ, SABR, HQx**)
carry copyleft licenses (GPLv3, GPLv2+, and LGPL2.1 respectively) with no exception that covers this
project, and the libretro slang-shaders ports commonly mistaken for "the permissive RetroArch version"
of xBRZ do not in fact relicense it — they carry the same GPLv3 notice forward.

Concretely, for Phase 1 (requirements §10, "1-pass mobile-lite tier... two-level classifier per
§6a.3"):

- The **3×3 binary-topology LUT** (§6a.3, explicitly modeled on "the HQx-portable part") must be
  built from an independently-derived truth table for the project's own edge-classification rules, not
  by copying HQx's or xBRZ's existing lookup tables or the comparison logic that generates them. The
  requirements document already frames this as a *general two-level decomposition technique*, not a
  reuse of any one algorithm's specific table — Phase 1 should keep it that way in practice, not just
  in framing.
- Any reconstruction-rule logic that resembles SABR's junction-ambiguity resolution or xBRZ's
  pattern-substitution rules must be written from the classifier's own FR2 region-class outputs and
  from published descriptions of the general technique, never by reading the SABR/xBRZ shader source
  with intent to reproduce its structure.
- ScaleFX and Omniscale source may be opened, read, and adapted freely during Phase 1 development;
  this is the one place in the pipeline where direct derivation is unambiguously safe.
- If a contributor is unsure whether a piece of Phase 1 code was written clean-room, the test is
  provenance, not similarity: was it written from a public algorithm description / the classifier's
  own derived statistics, or with the GPL/LGPL source open as a reference during writing? Only the
  former is safe under this determination.
- This determination should be linked from `CONTRIBUTING.md` once that file exists, per T-001's
  acceptance criteria, so future contributors see the clean-room requirement before touching
  edge-reconstruction code, not after.

This is a Phase-0 determination, not a final legal opinion — if the project later commits to a
GPL-compatible license for the whole codebase, the xBRZ/SABR/HQx verdicts above should be revisited,
since direct derivation would become available. Absent that decision, the conservative default (treat
all three as clean-room-only) is the one that keeps every future licensing choice open.
