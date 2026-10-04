"""Turn the ten pattern results into one ranked, de-duplicated, reconciled list of findings."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from finops import HOURS_PER_MONTH
from finops.datasets import load_focus
from finops.focus import CostRow, cost_by_resource
from finops.patterns import all_results
from finops.patterns.base import Finding, PatternResult

RISK_ORDER = {"low": 0, "medium": 1, "high": 2}
RECONCILE_TOLERANCE = 0.05
OBSERVED_HOURS = 720  # the FOCUS export covers 30 days


@dataclass
class EstateAnalysis:
    findings: list[Finding]
    results: list[PatternResult]
    billed_monthly: float
    conflicts: list[str] = field(default_factory=list)
    reconciliation: list[dict[str, Any]] = field(default_factory=list)

    @property
    def savings_monthly(self) -> float:
        return round(sum(f.savings_monthly for f in self.findings), 2)

    def by_id(self, fid: str) -> Finding:
        for f in self.findings:
            if f.id == fid:
                return f
        raise KeyError(fid)

    def by_pattern(self) -> dict[str, float]:
        out: dict[str, float] = defaultdict(float)
        for f in self.findings:
            out[f.pattern] += f.savings_monthly
        return {k: round(v, 2) for k, v in sorted(out.items())}


def dedupe(findings: list[Finding]) -> tuple[list[Finding], list[str]]:
    """Two findings that change the same resource in the same way cannot both ship: keep the larger."""
    seen: dict[tuple[str, str], Finding] = {}
    conflicts = []
    for f in findings:
        key = (f.resource_id, f.change.get("op", ""))
        if key in seen:
            keep, drop = (f, seen[key]) if f.savings_monthly > seen[key].savings_monthly else (seen[key], f)
            conflicts.append(
                f"{drop.id} ({drop.pattern}) dropped in favour of {keep.id} ({keep.pattern}) on {f.resource_name}"
            )
            seen[key] = keep
        else:
            seen[key] = f
    return list(seen.values()), conflicts


def reconcile(findings: list[Finding], rows: list[CostRow]) -> list[dict[str, Any]]:
    """Check each finding's 'current' cost against what the bill shows for that resource."""
    billed = cost_by_resource(rows)
    out = []
    for f in findings:
        if f.resource_id not in billed or f.current_monthly == 0:
            continue
        # the bill can include extra meters (egress, storage); only compare like for like
        if f.pattern not in {"p01-rightsize", "p07-serverless", "p08-idle-cleanup"}:
            continue
        projected = billed[f.resource_id] * HOURS_PER_MONTH / OBSERVED_HOURS
        gap = (f.current_monthly - projected) / projected
        out.append(
            {
                "finding": f.id,
                "resource": f.resource_name,
                "model": round(f.current_monthly, 2),
                "bill": round(projected, 2),
                "gap_pct": round(100 * gap, 2),
                "ok": abs(gap) <= RECONCILE_TOLERANCE,
            }
        )
    return out


def analyze_estate(
    results: list[PatternResult] | None = None, rows: list[CostRow] | None = None
) -> EstateAnalysis:
    results = results if results is not None else all_results()
    rows = rows if rows is not None else load_focus()
    raw = [f for r in results for f in r.findings if f.savings_monthly > 0 or f.pattern == "p08-idle-cleanup"]
    findings, conflicts = dedupe(raw)
    findings.sort(key=lambda f: (-f.savings_monthly, RISK_ORDER[f.risk], f.resource_name))
    billed = sum(r.cost for r in rows) * HOURS_PER_MONTH / OBSERVED_HOURS
    return EstateAnalysis(findings, results, round(billed, 2), conflicts, reconcile(findings, rows))
