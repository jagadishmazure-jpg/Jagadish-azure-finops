"""Eval-gated optimization: a cost cut ships only if quality holds.

Every optimization is described by its cost and its quality on the same eval set as the
baseline. The gate blocks a change if quality drops by more than ``max_quality_drop_pts`` or if
any safety case regresses, whatever it saves.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Candidate:
    name: str
    monthly_cost: float
    quality_pct: float
    safety_regressions: int = 0


@dataclass(frozen=True)
class Decision:
    name: str
    ship: bool
    savings: float
    quality_delta: float
    reason: str


def gate(baseline: Candidate, cand: Candidate, max_quality_drop_pts: float = 1.0) -> Decision:
    delta = round(cand.quality_pct - baseline.quality_pct, 2)
    savings = round(baseline.monthly_cost - cand.monthly_cost, 2)
    if cand.safety_regressions:
        return Decision(cand.name, False, savings, delta, f"{cand.safety_regressions} safety regression(s)")
    if delta < -max_quality_drop_pts:
        return Decision(
            cand.name,
            False,
            savings,
            delta,
            f"quality {delta:+.2f} pts exceeds the -{max_quality_drop_pts} pt budget",
        )
    if savings <= 0:
        return Decision(cand.name, False, savings, delta, "no saving")
    return Decision(cand.name, True, savings, delta, "quality within budget")
