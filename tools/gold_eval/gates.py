"""Numeric pass/fail gates for the vector-faithful reconstruction goal
(docs/requirements.md), drawn from the measured baseline table in
docs/backlog.md's "Scoring gates used below". Static reference thresholds,
not re-derived every run: xBRZ/SABR aren't always available to re-render
(fetched from scratch paths outside this repo, per run_eval.py's docstring),
so the gates are pinned to the published numbers in tools/gold_eval/
report.md rather than requiring a live competitor baseline on every run.
"""

# Vector-regime IoU%, per shape. Source: tools/gold_eval/report.md.
PRIMARY_GATE = {"v_corner": 93.4, "o_ring": 95.2}      # match xBRZ — the real target
INTERIM_GATE = {"v_corner": 88.9, "o_ring": 87.8}      # clear ScaleFX — proves the model works at all

# 8bit-regime IoU%, per shape — regression guard. Deliberately xBRZ's own
# 8bit score (87.6/84.7), NOT the retired prototype's (93.6/93.0): that
# number came from the nearest-neighbour-preserving path this project
# retired (docs/requirements.md v0.3), and gating on it would re-import the
# reversed goal. This guard only says: don't be worse than the competition
# at leaving genuinely blocky art alone.
REGRESSION_GUARD = {"v_corner": 87.6, "o_ring": 84.7}

GATES = (
    ("primary", "vector", PRIMARY_GATE),
    ("interim", "vector", INTERIM_GATE),
    ("regression_guard", "8bit", REGRESSION_GUARD),
)


def check_gates(results: dict, candidate: str) -> dict:
    """results: the {"vector": {...}, "8bit": {...}} structure run_eval.py
    builds, where each shape maps to {candidate_name: (iou, accuracy)}.

    Returns {gate_name: {shape_name: (score_pct, threshold_pct, passed)}},
    only for shapes where `candidate` actually has a score."""
    out = {}
    for gate_name, regime, thresholds in GATES:
        gate = {}
        for shape_name, threshold in thresholds.items():
            row = results.get(regime, {}).get(shape_name, {})
            if candidate not in row:
                continue
            score_pct = row[candidate][0] * 100.0
            gate[shape_name] = (score_pct, threshold, score_pct >= threshold)
        if gate:
            out[gate_name] = gate
    return out


def gate_passed(gate: dict) -> bool:
    return all(passed for _, _, passed in gate.values())


def format_gate_report(candidate: str, gate_results: dict) -> str:
    lines = [f"-- fidelity gates: {candidate} --"]
    for gate_name, _, _ in GATES:
        gate = gate_results.get(gate_name)
        if not gate:
            continue
        status = "PASS" if gate_passed(gate) else "FAIL"
        lines.append(f"[{status}] {gate_name}")
        for shape_name, (score_pct, threshold, passed) in gate.items():
            mark = "OK  " if passed else "MISS"
            lines.append(f"    {mark} {shape_name}: {score_pct:.1f}% (need >= {threshold:.1f}%)")
    return "\n".join(lines)
