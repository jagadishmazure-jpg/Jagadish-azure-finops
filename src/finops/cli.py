"""Command line entry point: ``finops <command>``.

    finops scan                 all ten patterns + the estate total
    finops pattern p05          one pattern
    finops ai                   AI FinOps report
    finops agent --top 5        ranked findings and a dry-run plan for the top N
    finops case-study           the anonymized idle-resources case study
    finops approve --plan ID --approver NAME --role finops-approver
    finops mcp                  run the FinOps agent as an MCP server (stdio)
"""

from __future__ import annotations

import argparse
import json
import sys
from importlib import import_module

from finops.patterns import MODULES


def estate_report(top: int = 10) -> str:
    from finops.agent.analyzer import analyze_estate
    from finops.patterns.base import money

    e = analyze_estate()
    L = ["== estate: Larkspur Freight (fictional), list-price snapshot"]
    L.append(f"  billed (30-day FOCUS export, projected to 730 h): {money(e.billed_monthly)}/mo")
    for p, v in e.by_pattern().items():
        L.append(f"  {p:<24} save {money(v):>10}/mo")
    L.append(f"  TOTAL proposed savings {money(e.savings_monthly)}/mo ({100 * e.savings_monthly / e.billed_monthly:.1f}% of the bill), {money(e.savings_monthly * 12)}/yr")
    L.append(f"  findings: {len(e.findings)}; conflicts resolved: {len(e.conflicts)}; reconciliation checks: "
             f"{sum(r['ok'] for r in e.reconciliation)}/{len(e.reconciliation)} within 5% of the bill")
    L.append(f"  top {top}:")
    for f in e.findings[:top]:
        L.append(f"    {f.id}  {f.resource_name:<26} {f.action:<52} save {money(f.savings_monthly):>9}/mo [{f.risk}]")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="finops")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scan")
    p = sub.add_parser("pattern")
    p.add_argument("id", help="p01 .. p10")
    p.add_argument("--evidence", action="store_true", help="also print each finding's evidence and change")
    sub.add_parser("ai")
    a = sub.add_parser("agent")
    a.add_argument("--top", type=int, default=5)
    sub.add_parser("case-study")
    ap_ = sub.add_parser("approve")
    ap_.add_argument("--plan", required=True)
    ap_.add_argument("--approver", required=True)
    ap_.add_argument("--role", required=True)
    ap_.add_argument("--hour", type=int, default=0, help="logical clock hour of the approval")
    sub.add_parser("mcp")
    args = ap.parse_args(argv)

    if args.cmd == "scan":
        for m in MODULES:
            print(import_module(f"finops.patterns.{m}").analyze().report())
        print(estate_report())
    elif args.cmd == "pattern":
        mod = next((m for m in MODULES if m.startswith(args.id)), None)
        if not mod:
            print(f"unknown pattern {args.id}; choose from {[m[:3] for m in MODULES]}", file=sys.stderr)
            return 2
        res = import_module(f"finops.patterns.{mod}").analyze()
        print(res.report())
        if args.evidence:
            for f in sorted(res.findings, key=lambda x: (-x.savings_monthly, x.resource_name)):
                print(f"  {f.id} {f.resource_name}")
                print(f"    evidence: {json.dumps(f.evidence, sort_keys=True)}")
                print(f"    change:   {json.dumps(f.change, sort_keys=True)}")
            if "policy" in res.extra:
                print("  generated policy:")
                print("\n".join("    " + line for line in json.dumps(res.extra["policy"], indent=2).splitlines()))
    elif args.cmd == "ai":
        from finops.ai.report import report

        print(report())
    elif args.cmd == "agent":
        from finops.agent.analyzer import analyze_estate
        from finops.agent.plan import build_plan

        print(estate_report(args.top))
        plan = build_plan(analyze_estate().findings[: args.top])
        print(f"  plan {plan.plan_id} (digest {plan.digest[:12]}...), {len(plan.steps)} steps, status {plan.status}:")
        for s in plan.steps:
            print(f"    [DRY-RUN when approved] {s.command}")
    elif args.cmd == "case-study":
        from finops.casestudy import run

        print(run())
    elif args.cmd == "approve":
        from finops.agent.approval import approve
        from finops.agent.mcp_server import approvals_dir
        from finops.agent.plan import plan_from_content

        src = approvals_dir() / f"{args.plan}.plan.json"
        if not src.exists():
            print(f"no drafted plan {args.plan} in {approvals_dir()}", file=sys.stderr)
            return 2
        plan = plan_from_content(json.loads(src.read_text()))
        a = approve(plan, args.approver, args.role, args.hour)
        out = approvals_dir() / f"{plan.plan_id}.{args.approver.split('@')[0]}.approval.json"
        out.write_text(json.dumps(a.__dict__, indent=1, sort_keys=True))
        print(f"approved {plan.plan_id} (digest {plan.digest[:12]}...) as {args.approver} [{args.role}] -> {out.name}")
    elif args.cmd == "mcp":
        from finops.agent.mcp_server import main as serve

        serve()
    return 0


if __name__ == "__main__":
    sys.exit(main())
