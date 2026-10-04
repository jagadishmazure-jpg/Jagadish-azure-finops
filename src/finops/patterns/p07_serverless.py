"""Pattern 7: serverless first. Pay per execution instead of for always-on plans.

Compares each always-on workload with its consumption equivalent at its measured volume:
  * Functions Premium (EP1, always at least one warm instance) vs Flex Consumption
    (GB-seconds and executions, with the monthly free grant in the price list);
  * Logic Apps Standard (WS1 plan) vs Logic Apps Consumption (per action; priced at the
    standard-connector action rate, which is an upper bound for built-in actions).

It recommends the move only when consumption is cheaper AND the workload has no hard blocker
(VNet integration the target cannot provide, or a cold-start budget below what it can meet).
High-volume workloads usually stay on a plan; the rule shows that too.
"""

from __future__ import annotations

from typing import Any

from finops.costing import monthly_cost
from finops.datasets import load_inventory
from finops.patterns.base import Finding, PatternResult
from finops.pricing import default_book

PATTERN = "p07-serverless"
FLEX_COLD_START_S = 3  # typical worst case without always-ready instances (seconds)


def flex_monthly(executions: int, duration_s: float, memory_gb: float) -> float:
    book = default_book()
    gb_s = executions * duration_s * memory_gb
    return book.tiered_cost("functions.flex.ondemand_gb_second", gb_s) + book.tiered_cost("functions.flex.ondemand_executions_10", executions / 10)


def logic_consumption_monthly(runs: int, actions_per_run: int) -> float:
    return runs * actions_per_run * default_book().price("logicapps.consumption.standard_action")


def blockers(p: dict[str, Any]) -> list[str]:
    out = []
    if p.get("needs_vnet"):
        out.append("needs VNet integration")
    if p.get("max_cold_start_s", 99) < FLEX_COLD_START_S:
        out.append(f"cold-start budget {p['max_cold_start_s']} s < {FLEX_COLD_START_S} s")
    return out


def analyze() -> PatternResult:
    book = default_book()
    res = PatternResult(PATTERN, "Serverless first: consumption instead of always-on plans", [])
    for r in load_inventory():
        p = r["properties"]
        if not r["type"].endswith("sites") or p.get("plan"):
            continue
        before = monthly_cost(r, book)
        if p.get("kind") == "functionapp":
            after = flex_monthly(p["monthly_executions"], p["avg_duration_s"], p["memory_gb"])
            target = "Functions Flex Consumption"
            ev = {"executions": p["monthly_executions"], "gb_seconds": p["monthly_executions"] * p["avg_duration_s"] * p["memory_gb"]}
        elif p.get("kind") == "workflowapp":
            after = logic_consumption_monthly(p["monthly_runs"], p["actions_per_run"])
            target = "Logic Apps Consumption"
            ev = {"runs": p["monthly_runs"], "actions": p["monthly_runs"] * p["actions_per_run"]}
        else:
            continue
        ev.update(always_on_monthly=round(before, 2), consumption_monthly=round(after, 2))
        if after >= before:
            res.skipped.append((r["name"], f"consumption would cost ${after:,.2f}/mo vs ${before:,.2f}/mo on {r['sku']}; keep the plan"))
            continue
        if b := blockers(p):
            res.skipped.append((r["name"], "blocked: " + ", ".join(b)))
            continue
        res.findings.append(Finding(
            PATTERN, r["id"], r["name"], f"{r['sku']} plan -> {target}", before, after, confidence="high", risk="low",
            change={"op": "migrate-hosting", "to": target}, evidence=ev,
        ))
    res.notes.append("Flex price includes the monthly free grant shown in the price list (first 100,000 GB-s and 250,000 executions)")
    return res
