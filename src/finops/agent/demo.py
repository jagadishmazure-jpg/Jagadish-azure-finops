"""A scripted MCP session against the FinOps agent, in process (``finops mcp-demo``).

Shows the whole loop an assistant would drive: discover tools, read the estate, pick idle-cleanup
findings, draft a plan, get refused without approval, then (as the humans) approve and dry-run.
The approvals are added the way ``finops approve`` would add them; the model has no tool for it.
"""

from __future__ import annotations

import asyncio
import json

from mcp import Client

from finops.agent import mcp_server as M
from finops.agent.approval import approve


def _data(result):
    if result.structured_content is not None:
        sc = result.structured_content
        return sc.get("result", sc)
    return json.loads(result.content[0].text)


async def _session() -> list[str]:
    M.STATE = M.State()
    out = []
    async with Client(M.server) as c:
        tools = (await c.list_tools()).tools
        out.append("tools: " + ", ".join(f"{t.name}{' (read-only)' if t.annotations.read_only_hint else ''}" for t in tools))
        s = _data(await c.call_tool("estate_summary", {}))
        out.append(f"estate_summary -> billed ${s['billed_monthly']:,.2f}/mo, savings ${s['savings_monthly']:,.2f}/mo, {s['findings']} findings")
        fs = _data(await c.call_tool("list_findings", {"pattern": "p08", "min_savings": 100}))
        out.append("list_findings(p08, >= $100) -> " + ", ".join(f"{f['id']} {f['resource']} ${f['savings_monthly']:,.2f}" for f in fs))
        e = _data(await c.call_tool("explain_finding", {"finding_id": fs[0]["id"]}))
        out.append(f"explain_finding({fs[0]['id']}) -> evidence {json.dumps(e['evidence'], sort_keys=True)}, doc {e['doc']}")
        p = _data(await c.call_tool("draft_change_plan", {"finding_ids": [f["id"] for f in fs]}))
        out.append(f"draft_change_plan -> {p['plan_id']} digest {p['digest'][:12]}..., ${p['savings_monthly']:,.2f}/mo, "
                   f"irreversible={p['irreversible']}, approvals_required={p['approvals_required']}")
        x = _data(await c.call_tool("execute_plan", {"plan_id": p["plan_id"]}))
        out.append(f"execute_plan (no approvals) -> refused: {x['refused']}")
        plan = M.STATE.plans[p["plan_id"]]
        M.STATE.approvals[p["plan_id"]] = [approve(plan, "owner@larkspur.example", "resource-owner", 1, M.STATE.audit)]
        st = _data(await c.call_tool("plan_status", {"plan_id": p["plan_id"]}))
        out.append(f"human 1 approves (resource-owner) -> plan_status problems: {st['problems']}")
        M.STATE.approvals[p["plan_id"]].append(approve(plan, "finops@larkspur.example", "finops-approver", 2, M.STATE.audit))
        x = _data(await c.call_tool("execute_plan", {"plan_id": p["plan_id"]}))
        out.append("human 2 approves (finops-approver) -> execute_plan dry_run=" + str(x["dry_run"]) + ":")
        out.extend(f"  {line}" for line in x["commands"])
        out.append(f"audit log: {len(M.STATE.audit.entries)} entries, chain verified={M.STATE.audit.verify()}")
    return out


def run() -> str:
    return "\n".join(asyncio.run(_session()))
