import pytest

from finops.costing import VM_SHAPES
from finops.patterns import p01_rightsize as P
from tests.conftest import find


@pytest.fixture(scope="module")
def res():
    return P.analyze()


def test_low_utilization_vms_step_down_one_size(res):
    assert find(res, "vm-dispatch-api-01").change["to"] == "D4s_v5"
    assert find(res, "vm-report-01").change["to"] == "D2s_v5"


def test_app_service_plan_is_rightsized(res):
    f = find(res, "asp-partner-api")
    assert f.change == {"op": "resize", "from": "P2v3", "to": "P1v3", "kind": "app-service-plan"}


def test_memory_bound_and_busy_hosts_are_left_alone(res):
    names = {n for n, _ in res.skipped}
    assert {"vm-dispatch-db-01", "vm-etl-01", "vm-build-01"} <= names
    assert not any(f.resource_name in {"vm-dispatch-db-01", "vm-etl-01", "vm-build-01"} for f in res.findings)


def test_weekly_spike_lowers_confidence(res):
    f = find(res, "vm-dispatch-api-02")
    assert f.confidence == "medium" and f.evidence["projected_cpu_peak"] > 100


def test_projected_p95_stays_within_target(res):
    for f in res.findings:
        assert f.evidence["projected_cpu_p95"] <= P.RULE["target_cpu_p95"]
        assert f.evidence["projected_mem_p95"] <= P.RULE["target_mem_p95"]


def test_stopped_vms_are_left_to_idle_cleanup(res):
    assert any(n == "vm-poc-gpu-replacement" and "p08" in why for n, why in res.skipped)


def test_short_history_is_not_enough():
    target, ev = P.recommend("D8s_v5", P.VM_LADDER["Dsv5"], VM_SHAPES, [5.0] * 100, [10.0] * 100)
    assert target == "D8s_v5" and "metrics" in ev["reason"]


def test_never_goes_below_smallest_size():
    target, _ = P.recommend("D2s_v5", P.VM_LADDER["Dsv5"], VM_SHAPES, [1.0] * 400, [5.0] * 400)
    assert target == "D2s_v5"


def test_headline_saving(res):
    assert res.savings_monthly == 713.94 and len(res.findings) == 5
