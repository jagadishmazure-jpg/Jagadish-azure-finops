"""Per-agent cost and value, in the shape of Agent 365 cost and value analytics.

Each agent in the synthetic log maps to one use case. Cost is the reconciled token spend.
Assisted hours and assisted value use the same adoption, minutes and loaded-rate assumptions as
ROI. Success rate is the simulated pass rate on the model the request actually called. Satisfaction
is a signal the product announcement lists and this log does not record, so it stays unset.

The routed columns reprice the same requests on the published GPT-6.2 route. They are a scenario,
not a second bill, and they are not an Azure or Bedrock price.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from finops.ai import catalog, routing
from finops.ai.roi import roi
from finops.ai.route_sim import model_for_route
from finops.ai.token_cost import cached_prefix_tokens, request_cost
from finops.datasets import load_ai_requests, load_json
from finops.patterns.base import money


def assisted(uc: dict[str, Any], tasks: float) -> tuple[float, float]:
    """Assisted hours and assisted value for ``tasks`` under the use-case assumptions."""
    hours = tasks * uc["adoption"] * uc["minutes_saved_per_task"] / 60
    return hours, hours * uc["loaded_rate_per_hour"]


def _routed_cost(rows: list[dict[str, Any]], prompt_cache: bool) -> float:
    total = 0.0
    for q in rows:
        cached = cached_prefix_tokens(q["system_prefix_tokens"]) if prompt_cache else 0
        total += (
            catalog.token_cost(model_for_route(q), q["prompt_tokens"], q["completion_tokens"], cached)
            * q["weight"]
        )
    return total


def build(reqs: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """One row per agent. Token cost uses the logged model and the list-price snapshot."""
    reqs = list(load_ai_requests() if reqs is None else reqs)
    cases = {u["use_case"]: u for u in load_json("ai/use-cases.json")}
    budgets = load_json("ai/budgets.json")["agent_monthly_usd"]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for q in reqs:
        grouped[q["agent"]].append(q)
    out = []
    for agent, rows in sorted(grouped.items()):
        names = {q["use_case"] for q in rows}
        if len(names) != 1:
            raise ValueError(f"{agent} maps to {sorted(names)}; expected one use case")
        uc = cases[names.pop()]
        tasks = sum(q["weight"] for q in rows)
        token = sum(request_cost(q) * q["weight"] for q in rows)
        ok = sum(q["weight"] for q in rows if routing.passes(q, q["model"]))
        hours, value = assisted(uc, tasks)
        loaded = roi(uc, tasks, token)
        routed = _routed_cost(rows, prompt_cache=False)
        routed_roi = roi(uc, tasks, routed)
        budget = budgets[agent]
        out.append(
            {
                "agent": agent,
                "use_case": uc["use_case"],
                "tasks": round(tasks),
                "token_cost": token,
                "budget": budget,
                "budget_pct": round(100 * token / budget, 1),
                "assisted_hours": hours,
                "assisted_value": value,
                "success_rate_pct": round(100 * ok / tasks, 2) if tasks else 0.0,
                "value_per_token_dollar": round(value / token, 2) if token else None,
                "satisfaction": None,
                "roi_pct": loaded["roi_pct"],
                "verdict": loaded["verdict"],
                "routed_token_cost": routed,
                "routed_cached_token_cost": _routed_cost(rows, prompt_cache=True),
                "routed_roi_pct": routed_roi["roi_pct"],
                "routed_verdict": routed_roi["verdict"],
            }
        )
    return out


def format_rows(rows: list[dict[str, Any]]) -> list[str]:
    lines = [
        "== per-agent cost and value",
        "  signals: token spend, assisted hours, assisted value, simulated success rate, ROI verdict.",
        "  satisfaction: not logged. routed $ is the published API scenario, not an Azure or Bedrock price.",
        f"  {'agent':<22} {'tasks':>7} {'token $':>10} {'asst h':>8} {'asst value':>12} "
        f"{'success':>8} {'value/$':>8} {'routed $':>10}  verdict",
    ]
    for r in rows:
        per = r["value_per_token_dollar"]
        per_s = f"{per:>8.1f}" if per is not None else f"{'n/a':>8}"
        lines.append(
            f"  {r['agent']:<22} {r['tasks']:>7,} {money(r['token_cost']):>10} {r['assisted_hours']:>8,.1f} "
            f"{money(r['assisted_value']):>12} {r['success_rate_pct']:>7.2f}% {per_s} "
            f"{money(r['routed_token_cost']):>10}  {r['verdict']}"
        )
        lines.append(
            f"    roi {r['roi_pct']:>7}% on logged-model tokens -> {r['routed_roi_pct']:>7}% "
            f"on routed API rates [{r['routed_verdict']}]"
        )
    return lines
