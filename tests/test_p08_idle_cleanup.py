import pytest

from finops.patterns import p08_idle_cleanup as P
from tests.conftest import find


@pytest.fixture(scope="module")
def res():
    return P.analyze()


def test_old_unattached_disks_found(res):
    f = find(res, "disk-migr-data-01")
    assert f.change == {"op": "delete", "pre": "snapshot"} and not f.reversible


def test_grace_period_protects_recent_leftovers(res):
    skipped = dict(res.skipped)
    assert "grace" in skipped["disk-dev-scratch-01"] and "grace" in skipped["pip-dev-lb-01"]


def test_exempt_tag_is_honoured(res):
    assert dict(res.skipped)["pip-migr-gw-02"] == "tagged finops-exempt=true"


def test_stopped_vm_gets_deallocated(res):
    f = find(res, "vm-poc-gpu-replacement")
    assert f.change["op"] == "deallocate" and f.reversible


def test_empty_plan_found(res):
    assert find(res, "asp-poc-empty").savings_monthly == pytest.approx(113.15)


def test_orphan_nic_is_hygiene_only(res):
    assert find(res, "nic-migr-vm-01").savings_monthly == 0


def test_plan_with_active_app_is_not_deleted():
    plan = {"id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Web/serverfarms/p", "name": "p", "type": "Microsoft.Web/serverfarms",
            "sku": "WS1", "tags": {}, "properties": {"kind": "workflowapp-plan", "apps": 1, "workflow_runs_30d": 0}}
    site = {"id": "x", "name": "s", "type": "Microsoft.Web/sites", "sku": "WS1", "tags": {},
            "properties": {"plan": plan["id"], "monthly_runs": 50, "actions_per_run": 3}}
    assert not P.detect([plan, site]).findings


def test_headline_saving(res):
    assert res.savings_monthly == 397.76
