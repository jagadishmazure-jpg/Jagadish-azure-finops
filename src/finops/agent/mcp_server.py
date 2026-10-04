"""The FinOps agent as an MCP server.

Tools an assistant (or any MCP client) can call:
  estate_summary      read-only   billed spend, savings by pattern
  list_findings       read-only   ranked findings, optional pattern / minimum saving filter
  explain_finding     read-only   evidence, decision rule and the doc to read
  draft_change_plan   read-only   builds a dry-run plan; it does NOT approve or change anything
  plan_status         read-only   approvals held vs required
  execute_plan        dry-run     refuses unless humans approved this exact plan content
  ai_cost_summary     read-only   token cost by tenant / agent / use case and the gated optimizations

There is deliberately no approval tool: approvals are given by people through the CLI
(``finops approve``), outside the model's reach.

    python -m finops.agent.mcp_server      # stdio transport
"""

from __future__ import annotations

import json
import os
from functools import cache
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from finops.agent.analyzer import EstateAnalysis, analyze_estate
from finops.agent.approval import Approval, ApprovalError, AuditLog, check, execute, required_approvals
from finops import ROOT
from finops.agent.plan import ChangePlan, build_plan

READ = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)
DRY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

server = MCPServer(
    "azure-finops-agent",
    instructions="Azure FinOps agent over a synthetic estate (Larkspur Freight, fictional). Proposes savings; never changes "
    "anything. Plans need human approval and execute as a dry run only.",
)


def approvals_dir() -> Path:
    return Path(os.environ.get("FINOPS_APPROVALS_DIR", ROOT / "approvals"))


class State:
    def __init__(self) -> None:
        self.plans: dict[str, ChangePlan] = {}
        self.approvals: dict[str, list[Approval]] = {}
        self.audit = AuditLog()
        self.clock_hour = 0  # logical clock; tests advance it
        self.persist = False  # the stdio entry point turns this on so the CLI can approve

    def save_plan(self, plan: ChangePlan) -> None:
        if self.persist:
            d = approvals_dir()
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{plan.plan_id}.plan.json").write_text(json.dumps(plan.content(), indent=1, sort_keys=True))

    def approvals_for(self, plan_id: str) -> list[Approval]:
        found = list(self.approvals.get(plan_id, []))
        if self.persist and approvals_dir().exists():
            for f in sorted(approvals_dir().glob(f"{plan_id}.*.approval.json")):
                found.append(Approval(**json.loads(f.read_text())))
        return found


STATE = State()


@cache
def estate() -> EstateAnalysis:
    return analyze_estate()


def doc_for(pattern: str) -> str:
    return f"docs/patterns/{pattern.split('-')[0][1:]}-{pattern.split('-', 1)[1]}.md"


@server.tool(annotations=READ)
def estate_summary() -> dict:
    """Billed monthly spend, total proposed savings and savings by pattern."""
    e = estate()
    return {"company": "Larkspur Freight (fictional)", "billed_monthly": e.billed_monthly, "savings_monthly": e.savings_monthly,
            "savings_pct": round(100 * e.savings_monthly / e.billed_monthly, 1), "by_pattern": e.by_pattern(),
            "findings": len(e.findings), "price_basis": "Azure Retail Prices list-price snapshot"}


@server.tool(annotations=READ)
def list_findings(pattern: str = "", min_savings: float = 0.0, limit: int = 50) -> list[dict]:
    """Ranked findings. Filter by pattern prefix (e.g. 'p08') and minimum monthly saving."""
    out = []
    for f in estate().findings:
        if pattern and not f.pattern.startswith(pattern):
            continue
        if f.savings_monthly < min_savings:
            continue
        out.append({"id": f.id, "pattern": f.pattern, "resource": f.resource_name, "action": f.action,
                    "savings_monthly": f.savings_monthly, "risk": f.risk, "confidence": f.confidence, "estimate": f.estimate})
    return out[:limit]


@server.tool(annotations=READ)
def explain_finding(finding_id: str) -> dict:
    """Evidence, proposed change and where the decision rule is documented."""
    try:
        f = estate().by_id(finding_id)
    except KeyError:
        return {"error": f"unknown finding {finding_id}"}
    return {**f.to_dict(), "doc": doc_for(f.pattern)}


@server.tool(annotations=READ)
def draft_change_plan(finding_ids: list[str]) -> dict:
    """Build a dry-run change plan for the given findings. Nothing is approved or changed."""
    e = estate()
    try:
        findings = [e.by_id(i) for i in finding_ids]
    except KeyError as exc:
        return {"error": f"unknown finding {exc.args[0]}"}
    plan = build_plan(findings)
    STATE.plans[plan.plan_id] = plan
    STATE.save_plan(plan)
    STATE.audit.append("plan-drafted", plan=plan.plan_id, digest=plan.digest, steps=len(plan.steps))
    return {"plan_id": plan.plan_id, "digest": plan.digest, "status": plan.status, "savings_monthly": plan.savings_monthly,
            "approvals_required": required_approvals(plan), "irreversible": plan.irreversible,
            "steps": [{"resource": s.resource, "action": s.action, "command": s.command, "rollback": s.rollback} for s in plan.steps],
            "next": "a human approves with: finops approve --plan <plan_id> --approver <name> --role finops-approver"}


@server.tool(annotations=READ)
def plan_status(plan_id: str) -> dict:
    """Approvals held, approvals required and any blocking problems."""
    plan = STATE.plans.get(plan_id)
    if not plan:
        return {"error": f"unknown plan {plan_id}"}
    held = STATE.approvals_for(plan_id)
    problems = check(plan, held, STATE.clock_hour)
    return {"plan_id": plan_id, "status": plan.status, "approvers": [a.approver for a in held],
            "required": required_approvals(plan), "problems": problems}


@server.tool(annotations=DRY)
def execute_plan(plan_id: str) -> dict:
    """Dry-run an approved plan: returns the commands that change management would run."""
    plan = STATE.plans.get(plan_id)
    if not plan:
        return {"error": f"unknown plan {plan_id}"}
    try:
        lines = execute(plan, STATE.approvals_for(plan_id), STATE.clock_hour, STATE.audit)
    except ApprovalError as exc:
        return {"plan_id": plan_id, "executed": False, "refused": str(exc)}
    return {"plan_id": plan_id, "executed": False, "dry_run": True, "commands": lines}


@server.tool(annotations=READ)
def ai_cost_summary() -> dict:
    """Token cost by tenant, agent and use case, and which AI optimizations passed the eval gate."""
    from finops.ai.report import analyze

    a = analyze()
    att = a["attribution"]
    return {"monthly_cost": round(att["total"], 2), "by_tenant": {k: round(v, 2) for k, v in att["by_tenant"].items()},
            "by_agent": {k: round(v, 2) for k, v in att["by_agent"].items()},
            "optimizations": [{"name": d.name, "ship": d.ship, "savings": d.savings, "quality_delta": d.quality_delta, "reason": d.reason}
                              for d in a["decisions"]]}


def main() -> None:
    STATE.persist = True
    server.run()


if __name__ == "__main__":
    main()
