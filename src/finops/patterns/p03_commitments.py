"""Pattern 3: commit the steady baseline with reservations or savings plans.

Input: hourly compute usage in normalized D2s_v5 units (instance size flexibility lets one
reservation cover D2/D4/D8 sizes in the family). Run AFTER rightsizing and autoscaling, so you do
not lock in waste.

For each option the optimal commitment level is found by brute force over every level and checked
against the analytic answer: commit up to the usage level that is exceeded in at least
(commitment rate / pay-as-you-go rate) of the hours. That fraction is also the break-even
utilization: a committed unit pays off only if it is used more than that share of the time.
"""

from __future__ import annotations

from dataclasses import dataclass

from finops import HOURS_PER_MONTH
from finops.datasets import load_compute_usage
from finops.patterns.base import Finding, PatternResult, money
from finops.pricing import PriceBook, default_book

PATTERN = "p03-commitments"
UNIT = "D2s_v5"
MAX_TERM_YEARS = 1  # policy: 3-year terms need an explicit roadmap sign-off


@dataclass(frozen=True)
class Option:
    name: str
    term_years: int
    hourly: float
    flexible: bool  # savings plans float across families/regions/services; reservations do not


def options(book: PriceBook) -> list[Option]:
    payg = f"vm.{UNIT}.linux.payg"
    return [
        Option("reservation-1y", 1, book.reservation_hourly(f"vm.{UNIT}.linux.ri1y"), False),
        Option("reservation-3y", 3, book.reservation_hourly(f"vm.{UNIT}.linux.ri3y"), False),
        Option("savings-plan-1y", 1, book.savings_plan_hourly(payg, "1 Year"), True),
        Option("savings-plan-3y", 3, book.savings_plan_hourly(payg, "3 Years"), True),
    ]


def cost_at(usage: list[float], level: int, rate: float, payg: float) -> float:
    return sum(level * rate + max(0.0, u - level) * payg for u in usage)


def best_level(usage: list[float], rate: float, payg: float) -> tuple[int, float]:
    levels = range(0, int(max(usage)) + 1)
    costs = {lv: cost_at(usage, lv, rate, payg) for lv in levels}
    lv = min(costs, key=lambda k: (costs[k], k))
    return lv, costs[lv]


def analytic_level(usage: list[float], rate: float, payg: float) -> int:
    """Largest level L such that usage >= L in at least rate/payg of the hours."""
    need = rate / payg
    n = len(usage)
    best = 0
    for lv in range(0, int(max(usage)) + 1):
        if sum(1 for u in usage if u >= lv) / n >= need:
            best = lv
    return best


def breakeven_months(rate: float, payg: float, term_years: int) -> float:
    """If the workload disappears after m months, savings so far equal the unused remainder when
    m = term x rate / payg."""
    return round(12 * term_years * rate / payg, 1)


def analyze(max_term_years: int = MAX_TERM_YEARS) -> PatternResult:
    book = default_book()
    usage = load_compute_usage()
    payg = book.price(f"vm.{UNIT}.linux.payg")
    scale = HOURS_PER_MONTH / len(usage)
    base_cost = cost_at(usage, 0, 0, payg) * scale
    table = []
    for o in options(book):
        lv, cost = best_level(usage, o.hourly, payg)
        table.append({"option": o.name, "term_years": o.term_years, "hourly": round(o.hourly, 5),
                      "discount_pct": round(100 * (1 - o.hourly / payg), 1), "level": lv,
                      "analytic_level": analytic_level(usage, o.hourly, payg), "monthly": round(cost * scale, 2),
                      "breakeven_utilization": round(o.hourly / payg, 3), "breakeven_months": breakeven_months(o.hourly, payg, o.term_years),
                      "flexible": o.flexible})
    allowed = [t for t in table if t["term_years"] <= max_term_years]
    pick = min(allowed, key=lambda t: (t["monthly"], not t["flexible"]))
    res = PatternResult(PATTERN, "Reservations and savings plans for the steady baseline", [], extra={"options": table, "usage_min": min(usage),
                        "usage_max": max(usage), "usage_avg": round(sum(usage) / len(usage), 2)})
    res.findings.append(Finding(
        PATTERN, "scope:/subscriptions/lk-prod", "D-series fleet (lk-prod)",
        f"buy {pick['option']} for {pick['level']} x {UNIT} units", base_cost, pick["monthly"],
        confidence="high", risk="medium" if pick["term_years"] > 1 else "low",
        change={"op": "purchase-commitment", "type": pick["option"], "quantity": pick["level"], "sku": UNIT, "scope": "shared"},
        evidence={"usage_min": min(usage), "usage_avg": res.extra["usage_avg"], "usage_max": max(usage), "pick": pick},
        reversible=False,
    ))
    for t in table:
        res.notes.append(
            f"{t['option']:<16} {t['discount_pct']:>5}% off  commit {t['level']:>2} units  month {money(t['monthly']):>10}  "
            f"break-even use {t['breakeven_utilization']:.0%}  break-even {t['breakeven_months']} months"
        )
    res.notes.append(f"policy max term {max_term_years}y -> {pick['option']}; usage min/avg/max {min(usage)}/{res.extra['usage_avg']}/{max(usage)} units")
    return res
