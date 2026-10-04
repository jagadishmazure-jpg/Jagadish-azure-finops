"""The FinOps agent: analysis, plans, approvals and the dry-run-only executor."""

import pytest

from finops.agent import approval as A
from finops.agent.analyzer import analyze_estate, dedupe
from finops.agent.plan import az_command, build_plan, plan_from_content
from finops.patterns.base import Finding


@pytest.fixture(scope="module")
def estate():
    return analyze_estate()


def _f(name="disk-x", op="delete", saving=10.0, pattern="p08-idle-cleanup", reversible=False):
    rid = f"/subscriptions/lk-nonprod/resourceGroups/rg-x/providers/Microsoft.Compute/disks/{name}"
    return Finding(pattern, rid, name, f"{op} {name}", saving, 0.0, change={"op": op}, reversible=reversible)


def test_estate_totals(estate):
    assert estate.savings_monthly == pytest.approx(sum(estate.by_pattern().values()))
    assert estate.billed_monthly > estate.savings_monthly > 0


def test_findings_ranked_by_saving(estate):
    s = [f.savings_monthly for f in estate.findings]
    assert s == sorted(s, reverse=True)


def test_every_pattern_with_money_contributes(estate):
    # p09 changes ownership, not price, so it carries no saving
    assert {k[:3] for k in estate.by_pattern()} == {f"p{i:02d}" for i in range(1, 11)} - {"p09"}


def test_model_reconciles_with_the_bill(estate):
    assert estate.reconciliation and all(r["ok"] for r in estate.reconciliation)


def test_dedupe_keeps_larger_conflicting_change():
    a, b = _f(saving=5), _f(saving=9, pattern="p01-rightsize")
    kept, conflicts = dedupe([a, b])
    assert kept == [b] and len(conflicts) == 1


def test_finding_ids_are_stable():
    assert _f().id == _f().id and _f().id.startswith("p08-")


def test_commands_for_each_op():
    assert az_command(_f()).startswith("az snapshot create")
    rid = "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1"
    f = Finding("p01-rightsize", rid, "vm1", "resize", 1, 0, change={"op": "resize", "kind": "vm", "to": "D2s_v5"})
    assert az_command(f) == "az vm resize -g rg -n vm1 --size Standard_D2s_v5"


def test_plan_digest_changes_with_content():
    p1, p2 = build_plan([_f()]), build_plan([_f(saving=11)])
    assert p1.plan_id == p2.plan_id and p1.digest != p2.digest


def test_plan_roundtrip():
    p = build_plan([_f()])
    assert plan_from_content(p.content()).digest == p.digest


def test_requester_cannot_self_approve():
    p = build_plan([_f()])
    with pytest.raises(A.ApprovalError):
        A.approve(p, "finops-agent", "finops-approver", 0)


def test_unknown_role_cannot_approve():
    with pytest.raises(A.ApprovalError):
        A.approve(build_plan([_f()]), "bob", "developer", 0)


def test_irreversible_plan_needs_two_people():
    p = build_plan([_f()])
    a1 = A.approve(p, "alice", "resource-owner", 0)
    assert "2 distinct" in A.check(p, [a1], 1)[0]
    assert A.check(p, [a1, A.approve(p, "bob", "finops-approver", 0)], 1) == []


def test_reversible_plan_needs_one():
    p = build_plan([_f(op="deallocate", reversible=True)])
    assert A.check(p, [A.approve(p, "alice", "resource-owner", 0)], 1) == []


def test_edited_plan_voids_approval():
    p = build_plan([_f(op="deallocate", reversible=True)])
    a = A.approve(p, "alice", "resource-owner", 0)
    p.steps[0].command = "az vm delete --yes"
    assert any("different plan content" in x for x in A.check(p, [a], 1))


def test_approvals_expire():
    p = build_plan([_f(op="deallocate", reversible=True)])
    a = A.approve(p, "alice", "resource-owner", 0)
    assert any("expired" in x for x in A.check(p, [a], A.APPROVAL_TTL_HOURS + 1))


def test_purchase_needs_finance():
    f = Finding("p03-commitments", "scope:x", "fleet", "buy", 10, 5, change={"op": "purchase-commitment", "type": "reservation-1y",
                "quantity": 2, "sku": "D2s_v5", "scope": "shared"}, reversible=False)
    p = build_plan([f])
    approvals = [A.approve(p, "alice", "resource-owner", 0), A.approve(p, "bob", "finops-approver", 0)]
    assert any("finance" in x for x in A.check(p, approvals, 1))


def test_executor_is_dry_run_only():
    p = build_plan([_f(op="deallocate", reversible=True)])
    a = A.approve(p, "alice", "resource-owner", 0)
    with pytest.raises(NotImplementedError):
        A.execute(p, [a], 1, dry_run=False)
    out = A.execute(p, [a], 1)
    assert out[0].startswith("[DRY-RUN]") and p.status == "dry-run-complete"


def test_refused_execution_is_audited_and_chain_verifies():
    log = A.AuditLog()
    p = build_plan([_f()])
    with pytest.raises(A.ApprovalError):
        A.execute(p, [], 0, audit=log)
    assert log.entries[-1]["event"] == "execution-refused" and log.verify()


def test_tampered_audit_chain_fails():
    log = A.AuditLog()
    log.append("a", x=1)
    log.append("b", x=2)
    log.entries[0]["data"]["x"] = 99
    assert not log.verify()
