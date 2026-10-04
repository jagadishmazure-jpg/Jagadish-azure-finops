"""The FinOps agent over MCP (in-process client), the case study and the CLI."""

import json

import pytest
from mcp import Client

from finops import cli
from finops.agent import mcp_server as M
from finops.agent.approval import approve
from finops.casestudy import run


def data(result):
    if result.structured_content is not None:
        sc = result.structured_content
        return sc.get("result", sc)
    return json.loads(result.content[0].text)


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    monkeypatch.setattr(M, "STATE", M.State())


async def test_tools_are_listed_with_read_only_hints():
    async with Client(M.server) as c:
        tools = {t.name: t for t in (await c.list_tools()).tools}
    assert set(tools) == {"estate_summary", "list_findings", "explain_finding", "draft_change_plan", "plan_status", "execute_plan", "ai_cost_summary"}
    assert "approve" not in " ".join(tools)
    assert all(t.annotations.read_only_hint for t in tools.values())


async def test_summary_and_filtered_findings():
    async with Client(M.server) as c:
        s = data(await c.call_tool("estate_summary", {}))
        f = data(await c.call_tool("list_findings", {"pattern": "p08", "min_savings": 100}))
    assert s["savings_monthly"] > 0 and s["price_basis"].startswith("Azure Retail Prices")
    assert f and all(x["pattern"].startswith("p08") and x["savings_monthly"] >= 100 for x in f)


async def test_explain_points_to_the_doc():
    async with Client(M.server) as c:
        fid = data(await c.call_tool("list_findings", {"pattern": "p05"}))[0]["id"]
        e = data(await c.call_tool("explain_finding", {"finding_id": fid}))
        bad = data(await c.call_tool("explain_finding", {"finding_id": "nope"}))
    assert e["doc"] == "docs/patterns/05-storage-tiering.md" and "evidence" in e
    assert "error" in bad


async def test_execute_refused_until_humans_approve():
    async with Client(M.server) as c:
        ids = [x["id"] for x in data(await c.call_tool("list_findings", {"pattern": "p08", "min_savings": 100}))]
        plan = data(await c.call_tool("draft_change_plan", {"finding_ids": ids}))
        refused = data(await c.call_tool("execute_plan", {"plan_id": plan["plan_id"]}))
        p = M.STATE.plans[plan["plan_id"]]
        M.STATE.approvals[p.plan_id] = [approve(p, "alice", "resource-owner", 0), approve(p, "bob", "finops-approver", 0)]
        status = data(await c.call_tool("plan_status", {"plan_id": plan["plan_id"]}))
        done = data(await c.call_tool("execute_plan", {"plan_id": plan["plan_id"]}))
    assert plan["approvals_required"] == 2 and "refused" in refused and refused["executed"] is False
    assert status["problems"] == []
    assert done["dry_run"] is True and done["executed"] is False and all(x.startswith("[DRY-RUN]") for x in done["commands"])
    assert M.STATE.audit.verify()


async def test_unknown_ids_are_errors():
    async with Client(M.server) as c:
        assert "error" in data(await c.call_tool("draft_change_plan", {"finding_ids": ["nope"]}))
        assert "error" in data(await c.call_tool("plan_status", {"plan_id": "nope"}))
        assert "error" in data(await c.call_tool("execute_plan", {"plan_id": "nope"}))


async def test_ai_cost_summary_tool():
    async with Client(M.server) as c:
        s = data(await c.call_tool("ai_cost_summary", {}))
    assert s["monthly_cost"] > 0 and any(o["ship"] for o in s["optimizations"]) and any(not o["ship"] for o in s["optimizations"])


def test_cli_approval_roundtrip(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FINOPS_APPROVALS_DIR", str(tmp_path))
    M.STATE.persist = True
    fid = M.estate().findings[0].id
    plan = M.draft_change_plan([fid])
    assert cli.main(["approve", "--plan", plan["plan_id"], "--approver", "carol@larkspur.example", "--role", "finops-approver"]) == 0
    assert len(M.STATE.approvals_for(plan["plan_id"])) == 1
    assert "approved" in capsys.readouterr().out


def test_cli_rejects_unknown_plan(tmp_path, monkeypatch):
    monkeypatch.setenv("FINOPS_APPROVALS_DIR", str(tmp_path))
    assert cli.main(["approve", "--plan", "plan-none", "--approver", "x", "--role", "finops-approver"]) == 2


def test_cli_scan_and_pattern(capsys):
    assert cli.main(["pattern", "p07"]) == 0
    assert "p07-serverless" in capsys.readouterr().out
    assert cli.main(["pattern", "p99"]) == 2


def test_case_study_reproduces_the_reviewed_numbers():
    out = run()
    assert "$0.2399/h" in out and "$175.16/mo" in out and "$11.83/mo" in out
    assert "refused" in out and "verified=True" in out


def test_case_study_has_no_real_identifiers():
    from finops.datasets import load_json

    text = json.dumps(load_json("case-study/inventory.json"))
    assert "cs-practice" in text and "acloud" not in text and "myagent" not in text
