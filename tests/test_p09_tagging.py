import pytest

from finops.datasets import load_focus, load_json
from finops.patterns import p09_tagging_chargeback as P


@pytest.fixture(scope="module")
def res():
    return P.analyze()


def test_compliance_measures_cost_not_count(res):
    c = res.extra["compliance"]
    assert 0 < c["tagged_cost_pct"] < 100 and "disk-migr-data-01" in c["untagged_resources"]


def test_showback_adds_up_to_the_bill(res):
    total = sum(v["total"] for v in res.extra["showback"].values())
    assert total == pytest.approx(sum(r.cost for r in load_focus()), abs=0.05)


def test_shared_cost_split_proportionally(res):
    sb = res.extra["showback"]
    ratio = {cc: v["shared"] / v["direct"] for cc, v in sb.items() if cc != "unallocated"}
    assert max(ratio.values()) - min(ratio.values()) < 1e-3


def test_untagged_resources_get_owner_from_rg_map():
    rules = load_json("allocation/rules.json")
    row = next(r for r in load_focus() if r.resource_name == "disk-migr-data-01")
    assert P.owner_of(row, rules) == ("CC-4004", "resource-group map")


def test_nothing_unallocated(res):
    assert "unallocated" not in res.extra["showback"]


def test_budget_breach_is_forecast(res):
    b = {x["cost_center"]: x for x in res.extra["budgets"]}
    assert "100%" in b["CC-3003"]["alerts"] and "100%" not in b["CC-1001"]["alerts"]


def test_forecast_uses_allocated_cost(res):
    b = {x["cost_center"]: x for x in res.extra["budgets"]}
    assert b["CC-4004"]["forecast"] == pytest.approx(res.extra["showback"]["CC-4004"]["total"], rel=0.02)
