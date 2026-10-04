"""Synthetic data: deterministic, current, FOCUS-shaped, and free of real identifiers."""

import re

from finops import DATA
from finops import focus as F
from finops import synth as S
from finops.costing import container_app_monthly, logic_apps_standard_hourly, monthly_cost
from finops.datasets import generate_all, load_focus


def test_checked_in_data_matches_generator():
    for rel, text in generate_all().items():
        assert (DATA / rel).read_text() == text, f"data/{rel} is stale; run scripts/generate_data.py"


def test_generator_is_deterministic():
    assert S.utilization(S.inventory()) == S.utilization(S.inventory())
    assert S.ai_requests()[:50] == S.ai_requests()[:50]


def test_no_subscription_guids_anywhere_in_data():
    guid = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
    for rel in generate_all():
        assert not guid.search((DATA / rel).read_text()), rel


def test_subscriptions_are_aliases(inventory):
    assert {r["subscription"] for r in inventory} == {"lk-prod", "lk-nonprod"}


def test_focus_export_has_the_columns():
    header = (DATA / "focus/cost-export.csv").read_text().splitlines()[0].split(",")
    assert header == F.COLUMNS
    for col in ("BilledCost", "EffectiveCost", "ListCost", "ChargePeriodStart", "ResourceId", "Tags"):
        assert col in header


def test_focus_reader_rejects_other_formats():
    import pytest

    with pytest.raises(ValueError):
        F.read("a,b\n1,2\n")


def test_focus_covers_thirty_days():
    assert len({r.day for r in load_focus()}) == 30


def test_ws1_hourly_matches_the_reviewed_case(book):
    assert round(logic_apps_standard_hourly("WS1", book), 4) == 0.2399
    assert round(logic_apps_standard_hourly("WS1", book) * 730, 2) == 175.16


def test_container_app_warm_replica_costs_money_with_zero_traffic(book):
    assert round(container_app_monthly(1, 0.5, 1.0, 0.0, 0, book), 2) == 11.83
    assert container_app_monthly(0, 0.5, 1.0, 0.0, 0, book) == 0


def test_deallocated_vm_has_no_compute_cost(inventory, book):
    r = next(x for x in inventory if x["name"] == "vm-poc-old-ui")
    assert monthly_cost(r, book) == 0


def test_sql_license_is_part_of_vm_cost(inventory, book):
    r = next(x for x in inventory if x["name"] == "vm-dispatch-db-01")
    assert round(monthly_cost(r, book), 2) == round((0.436 + 0.4) * 730, 2)


def test_ai_log_is_a_weighted_sample():
    reqs = S.ai_requests()
    assert len(reqs) == 6000 and all(r["weight"] == S.AI_SAMPLE_WEIGHT for r in reqs)
