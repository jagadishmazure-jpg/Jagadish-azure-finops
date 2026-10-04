import pytest
import yaml

from finops.patterns import p02_autoscale as P
from tests.conftest import find


@pytest.fixture(scope="module")
def res():
    return P.analyze()


def test_instance_math():
    assert P.instances_needed(0, 250) == P.APP_MIN
    assert P.instances_needed(10_000, 250) == P.APP_MAX
    assert P.instances_needed(900, 250) == 6


def test_static_count_matches_replayed_peak(res):
    f = find(res, "asp-portal-prod")
    assert f.evidence["replayed_peak_instances"] == f.evidence["fixed_instances"] == 6
    assert f.evidence["replayed_avg_instances"] < 3


def test_aks_autoscaler_finding(res):
    f = find(res, "aks-dispatch-prod")
    assert f.change["op"] == "enable-cluster-autoscaler" and f.change["min"] == 2
    hpa = yaml.safe_load(f.change["hpa"])
    assert hpa["kind"] == "HorizontalPodAutoscaler" and hpa["spec"]["minReplicas"] == 2


def test_dev_container_apps_scale_to_zero(res):
    api = find(res, "ca-dispatch-dev-api")
    worker = find(res, "ca-dispatch-dev-worker")
    assert api.change["scale"]["minReplicas"] == 0 and worker.change["scale"]["minReplicas"] == 0
    keda = yaml.safe_load(worker.change["keda"])
    assert keda["spec"]["minReplicaCount"] == 0 and keda["spec"]["triggers"][0]["type"] == "azure-servicebus"


def test_prod_app_with_latency_slo_keeps_warm_replica(res):
    assert any(n == "ca-eta-assistant" for n, _ in res.skipped)


def test_autoscale_profile_shape():
    prof = P.app_service_autoscale_profile(250)
    assert prof["capacity"]["minimum"] == "2" and len(prof["rules"]) == 2
    assert {r["scaleAction"]["direction"] for r in prof["rules"]} == {"Increase", "Decrease"}


def test_headline_saving(res):
    assert res.savings_monthly == 811.80
