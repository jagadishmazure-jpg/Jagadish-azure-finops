"""ROI per AI use case: value delivered vs everything it costs to run.

value/month  = tasks x adoption x minutes saved / 60 x loaded hourly rate
cost/month   = model tokens (from attribution) + platform share + build cost / amortization months
ROI          = (value - cost) / cost
payback      = build cost / (value - run cost), in months (run cost excludes amortization)

Minutes saved, adoption and loaded rate are ASSUMPTIONS agreed with the business owner; they are
the inputs a FinOps or ROI coach should challenge first. Task counts come from the request log.
"""

from __future__ import annotations

from typing import Any


def roi(uc: dict[str, Any], tasks: float, token_monthly: float) -> dict[str, Any]:
    value = tasks * uc["adoption"] * uc["minutes_saved_per_task"] / 60 * uc["loaded_rate_per_hour"]
    run = token_monthly + uc["platform_monthly"]
    amort = uc["build_cost"] / uc["amortize_months"]
    cost = run + amort
    margin = value - run
    r = (value - cost) / cost
    verdict = "scale" if r >= 1 else ("keep and optimize" if r >= 0 else "rework or retire")
    return {
        "use_case": uc["use_case"],
        "tasks": round(tasks),
        "value": round(value, 2),
        "token_cost": round(token_monthly, 2),
        "platform": uc["platform_monthly"],
        "amortized_build": round(amort, 2),
        "total_cost": round(cost, 2),
        "roi_pct": round(100 * r, 1),
        "payback_months": round(uc["build_cost"] / margin, 1) if margin > 0 else None,
        "cost_per_task": round(cost / tasks, 4) if tasks else None,
        "verdict": verdict,
    }
