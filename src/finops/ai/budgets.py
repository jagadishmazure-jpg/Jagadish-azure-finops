"""Budget guardrails per tenant and per agent, enforced at request time.

Spend is tracked as requests arrive (weighted monthly cost). Thresholds come from
``data/ai/budgets.json``:
  * soft alert (80 %): notify the owner once;
  * degrade (100 %): non-critical agents are routed to the small model;
  * block (120 %): non-critical agents return a "budget reached" fallback instead of calling a
    model. Critical agents are never blocked; their owner is paged instead.
Whichever of tenant or agent is further over its budget decides.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from finops.ai.routing import SMALL
from finops.ai.token_cost import request_cost


def enforce(requests: list[dict[str, Any]], cfg: dict[str, Any]) -> dict[str, Any]:
    spend_t: dict[str, float] = defaultdict(float)
    spend_a: dict[str, float] = defaultdict(float)
    alerts: list[str] = []
    alerted: set[str] = set()
    counts = {"normal": 0, "degraded": 0, "blocked": 0, "critical_over_budget": 0}
    total = 0.0
    for q in sorted(requests, key=lambda r: (r["day"], r["request_id"])):
        t, a = q["tenant"], q["agent"]
        ratio = max(spend_t[t] / cfg["tenant_monthly_usd"][t], spend_a[a] / cfg["agent_monthly_usd"][a])
        critical = a in cfg["critical_agents"]
        for who, spent, budget in ((f"tenant:{t}", spend_t[t], cfg["tenant_monthly_usd"][t]), (f"agent:{a}", spend_a[a], cfg["agent_monthly_usd"][a])):
            for level, name in ((cfg["soft_alert"], "80%"), (cfg["degrade_at"], "100%"), (cfg["block_at"], "120%")):
                if spent >= budget * level and (who, name) not in alerted:
                    alerted.add((who, name))
                    alerts.append(f"day {q['day']:>2}: {who} reached {name} of ${budget:,.0f}")
        if ratio >= cfg["block_at"] and not critical:
            counts["blocked"] += 1
            continue
        model = q["model"]
        if ratio >= cfg["degrade_at"]:
            if critical:
                counts["critical_over_budget"] += 1
            else:
                model = SMALL
                counts["degraded"] += 1
        else:
            counts["normal"] += 1
        c = request_cost(q, model) * q["weight"]
        spend_t[t] += c
        spend_a[a] += c
        total += c
    return {"total": total, "counts": counts, "alerts": alerts, "spend_tenant": dict(spend_t), "spend_agent": dict(spend_a)}
