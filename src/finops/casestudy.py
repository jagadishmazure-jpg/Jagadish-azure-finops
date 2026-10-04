"""Case study: an anonymized reproduction of a pattern found in a real cost review.

What was seen: a practice subscription kept a Logic Apps Standard WS1 plan running with no
workflow runs, and a Container App with minReplicas=1 serving no traffic. Neither looked
expensive in the portal, but both bill around the clock. The resources, names and subscription
here are synthetic; only the shape of the problem is real.
"""

from __future__ import annotations

from finops import HOURS_PER_MONTH, SECONDS_PER_MONTH
from finops.agent.approval import ApprovalError, AuditLog, approve, execute
from finops.agent.plan import build_plan
from finops.datasets import load_json
from finops.patterns.base import money
from finops.patterns.p08_idle_cleanup import detect
from finops.pricing import default_book


def run() -> str:
    book = default_book()
    inv = load_json("case-study/inventory.json")
    vcpu_h, gib_h = book.price("logicapps.standard.vcpu_hour"), book.price("logicapps.standard.gib_hour")
    ws1_hour = vcpu_h + 3.5 * gib_h
    idle_rate = 0.5 * book.price("containerapps.vcpu_idle_second") + 1.0 * book.price("containerapps.gib_idle_second")
    L = ["== case study: idle Logic Apps Standard WS1 plan + Container App held warm (anonymized, synthetic data)"]
    L.append(f"  WS1 = 1 vCPU x ${vcpu_h}/h + 3.5 GiB x ${gib_h}/h = ${ws1_hour:.4f}/h -> x {HOURS_PER_MONTH} h = {money(ws1_hour * HOURS_PER_MONTH)}/mo")
    L.append(f"  Container App idle replica (0.5 vCPU, 1 GiB) = ${idle_rate:.7f}/s x {SECONDS_PER_MONTH:,} s = {money(idle_rate * SECONDS_PER_MONTH)}/mo")
    res = detect(inv, book, pattern="case-study")
    for f in res.findings:
        L.append(f"  finding {f.id}: {f.resource_name}: {f.action}: {money(f.current_monthly)} -> {money(f.proposed_monthly)}")
    total = sum(f.savings_monthly for f in res.findings)
    L.append(f"  total: save {money(total)}/mo, {money(total * 12)}/yr")
    plan = build_plan(res.findings, requested_by="finops-agent")
    audit = AuditLog()
    L.append(f"  plan {plan.plan_id}: {len(plan.steps)} step(s), irreversible={plan.irreversible}, needs 2 approvers")
    try:
        execute(plan, [], now_hour=1, audit=audit)
    except ApprovalError as exc:
        L.append(f"  execute without approval -> refused: {exc}")
    a1 = approve(plan, "owner@larkspur.example", "resource-owner", now_hour=2, audit=audit)
    a2 = approve(plan, "finops@larkspur.example", "finops-approver", now_hour=3, audit=audit)
    for line in execute(plan, [a1, a2], now_hour=4, audit=audit):
        L.append(f"  {line}")
    L.append(f"  audit chain: {len(audit.entries)} entries, verified={audit.verify()}")
    L.append("  lesson: idle cost hides in 'always-on' SKUs; detect by usage (runs, requests), not by resource count")
    return "\n".join(L)
