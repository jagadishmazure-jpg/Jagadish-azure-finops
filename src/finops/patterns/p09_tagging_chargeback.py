"""Pattern 9: tagging, budgets, showback and chargeback by cost center.

Works only from the FOCUS cost export plus a small rules file, the same inputs a FinOps team has:
  1. Tag compliance: share of cost carrying every required tag.
  2. Allocation: the ``cost-center`` tag first, then a resource-group owner map for untagged
     resources, else "unallocated" (the number to drive to zero).
  3. Shared costs (the platform Log Analytics workspace) are split in proportion to each cost
     center's direct spend.
  4. Budgets: a mid-month run-rate forecast is compared with each budget and alert thresholds.

The "saving" here is not a price change. Accountability is the lever; the finding records the
unallocated spend that gets an owner, and the budget alerts that would fire.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from finops.datasets import load_focus, load_json
from finops.focus import CostRow
from finops.patterns.base import Finding, PatternResult, money

PATTERN = "p09-tagging-chargeback"
FORECAST_DAY = 15


def compliance(rows: list[CostRow], required: list[str]) -> dict[str, Any]:
    total = sum(r.cost for r in rows)
    ok = sum(r.cost for r in rows if all(k in r.tags for k in required))
    missing = sorted({r.resource_name for r in rows if not all(k in r.tags for k in required)})
    return {
        "tagged_cost_pct": round(100 * ok / total, 1),
        "untagged_resources": missing,
        "untagged_cost": round(total - ok, 2),
    }


def owner_of(row: CostRow, rules: dict[str, Any]) -> tuple[str, str]:
    if cc := row.tags.get("cost-center"):
        return cc, "tag"
    rg = row.resource_id.split("/resourceGroups/")[1].split("/")[0]
    if cc := rules["resource_group_owner"].get(rg):
        return cc, "resource-group map"
    return "unallocated", "none"


def showback(rows: list[CostRow], rules: dict[str, Any]) -> dict[str, dict[str, float]]:
    shared_ids = {k.split("/")[1] for k in rules["shared"]}
    direct: dict[str, float] = defaultdict(float)
    shared_pool = 0.0
    for r in rows:
        if r.resource_name in shared_ids:
            shared_pool += r.cost
            continue
        direct[owner_of(r, rules)[0]] += r.cost
    base = sum(v for k, v in direct.items() if k != "unallocated")
    out = {}
    for cc in sorted(direct):
        share = 0.0 if cc == "unallocated" else shared_pool * direct[cc] / base
        out[cc] = {
            "direct": round(direct[cc], 2),
            "shared": round(share, 2),
            "total": round(direct[cc] + share, 2),
        }
    return out


def budget_status(
    rows: list[CostRow], rules: dict[str, Any], day: int = FORECAST_DAY
) -> list[dict[str, Any]]:
    """Budgets are checked against ALLOCATED cost (direct + shared share), the number a cost
    center is charged, using a straight-line forecast from the first ``day`` days."""
    days = sorted({r.day for r in rows})
    mtd_days = set(days[:day])
    alloc = showback([r for r in rows if r.day in mtd_days], rules)
    out = []
    for cc, budget in sorted(rules["budgets"].items()):
        mtd = {k: v["total"] for k, v in alloc.items()}.get(cc, 0.0)
        forecast = mtd / day * len(days)
        hit = [t for t in rules["alert_thresholds"] if forecast >= budget * t]
        out.append(
            {
                "cost_center": cc,
                "budget": budget,
                "mtd": round(mtd, 2),
                "forecast": round(forecast, 2),
                "forecast_pct": round(100 * forecast / budget, 1),
                "alerts": [f"{int(t * 100)}%" for t in hit],
            }
        )
    return out


def analyze() -> PatternResult:
    rows = load_focus()
    rules = load_json("allocation/rules.json")
    comp = compliance(rows, rules["required_tags"])
    sb = showback(rows, rules)
    budgets = budget_status(rows, rules)
    res = PatternResult(
        PATTERN,
        "Tagging, showback/chargeback and budgets",
        [],
        extra={"compliance": comp, "showback": sb, "budgets": budgets},
    )
    mapped = defaultdict(float)
    for r in rows:
        cc, how = owner_of(r, rules)
        if how == "resource-group map":
            mapped[r.resource_name] += r.cost
    for name, cost in sorted(mapped.items()):
        res.findings.append(
            Finding(
                PATTERN,
                f"tag:{name}",
                name,
                "add cost-center tag (owner from resource-group map)",
                round(cost, 2),
                round(cost, 2),
                change={"op": "tag", "tags": {"cost-center": "from-rg-map"}},
                evidence={"monthly_cost_now_allocated": round(cost, 2)},
            )
        )
    res.notes.append(
        f"tag compliance: {comp['tagged_cost_pct']}% of cost has all required tags; untagged cost {money(comp['untagged_cost'])}"
    )
    for cc, v in sb.items():
        res.notes.append(
            f"showback {cc:<12} direct {money(v['direct']):>10}  shared {money(v['shared']):>9}  total {money(v['total']):>10}"
        )
    for b in budgets:
        res.notes.append(
            f"budget {b['cost_center']}: day-{FORECAST_DAY} forecast {money(b['forecast'])} = {b['forecast_pct']}% of {money(b['budget'])} -> alerts {b['alerts'] or 'none'}"
        )
    return res
