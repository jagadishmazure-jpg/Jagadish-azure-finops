"""Shared result types and a plain-text report renderer for the patterns."""

from __future__ import annotations

import hashlib
import math
from dataclasses import asdict, dataclass, field
from typing import Any


def money(x: float) -> str:
    return f"${x:,.2f}"


def percentile(values: list[float], p: float) -> float:
    """Nearest-rank percentile (the method Azure Advisor-style rules usually describe)."""
    if not values:
        raise ValueError("no values")
    s = sorted(values)
    k = max(0, math.ceil(p / 100 * len(s)) - 1)
    return s[k]


@dataclass
class Finding:
    pattern: str
    resource_id: str
    resource_name: str
    action: str
    current_monthly: float
    proposed_monthly: float
    confidence: str = "high"  # high | medium | low
    risk: str = "low"  # low | medium | high
    change: dict[str, Any] = field(default_factory=dict)  # machine-readable proposed change
    evidence: dict[str, Any] = field(default_factory=dict)
    reversible: bool = True
    estimate: bool = False  # True when the saving rests on an assumption, not only list prices

    @property
    def savings_monthly(self) -> float:
        return round(self.current_monthly - self.proposed_monthly, 2)

    @property
    def id(self) -> str:
        raw = f"{self.pattern}|{self.resource_id}|{self.action}"
        return f"{self.pattern.split('-')[0]}-{hashlib.sha256(raw.encode()).hexdigest()[:8]}"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["id"] = self.id
        d["savings_monthly"] = self.savings_monthly
        d["current_monthly"] = round(self.current_monthly, 2)
        d["proposed_monthly"] = round(self.proposed_monthly, 2)
        return d


@dataclass
class PatternResult:
    pattern: str
    title: str
    findings: list[Finding]
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (resource, reason)
    notes: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def current_monthly(self) -> float:
        return round(sum(f.current_monthly for f in self.findings), 2)

    @property
    def savings_monthly(self) -> float:
        return round(sum(f.savings_monthly for f in self.findings), 2)

    @property
    def savings_pct(self) -> float:
        return round(100 * self.savings_monthly / self.current_monthly, 1) if self.current_monthly else 0.0

    def report(self) -> str:
        lines = [f"== {self.pattern}: {self.title}"]
        if self.findings:
            w = max(len(f.resource_name) for f in self.findings)
            for f in sorted(self.findings, key=lambda x: (-x.savings_monthly, x.resource_name)):
                tag = " (estimate)" if f.estimate else ""
                lines.append(
                    f"  {f.resource_name:<{w}}  {f.action:<46} {money(f.current_monthly):>11} -> {money(f.proposed_monthly):>10}"
                    f"  save {money(f.savings_monthly):>10}/mo  [{f.confidence}/{f.risk}]{tag}"
                )
        for name, why in self.skipped:
            lines.append(f"  skip {name}: {why}")
        for n in self.notes:
            lines.append(f"  note: {n}")
        lines.append(
            f"  TOTAL: {len(self.findings)} finding(s), {money(self.current_monthly)} -> "
            f"{money(self.current_monthly - self.savings_monthly)}, save {money(self.savings_monthly)}/mo "
            f"({self.savings_pct}%), {money(self.savings_monthly * 12)}/yr"
        )
        return "\n".join(lines)
