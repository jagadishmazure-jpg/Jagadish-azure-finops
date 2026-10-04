import pytest

from finops.patterns import p07_serverless as P
from tests.conftest import find


@pytest.fixture(scope="module")
def res():
    return P.analyze()


def test_low_volume_logic_app_moves_to_consumption(res):
    f = find(res, "la-invoice-intake")
    assert f.current_monthly == pytest.approx(175.16, abs=0.01) and f.proposed_monthly == pytest.approx(3.0)


def test_low_volume_function_fits_free_grant(res):
    assert find(res, "fn-label-print").proposed_monthly == 0


def test_high_volume_function_stays_on_plan(res):
    assert any(n == "fn-telemetry-ingest" and "keep the plan" in why for n, why in res.skipped)


def test_flex_price_grows_with_volume():
    assert P.flex_monthly(1_000_000_000, 0.25, 0.5) > P.flex_monthly(1_000_000, 0.25, 0.5)


def test_blockers():
    assert P.blockers({"needs_vnet": True}) == ["needs VNet integration"]
    assert P.blockers({"max_cold_start_s": 1})
    assert P.blockers({}) == []


def test_blocked_workload_is_skipped(monkeypatch):
    from finops.datasets import load_inventory

    inv = [dict(r, properties={**r["properties"], "needs_vnet": True}) if r["name"] == "fn-label-print" else r for r in load_inventory()]
    monkeypatch.setattr(P, "load_inventory", lambda: inv)
    out = P.analyze()
    assert any(n == "fn-label-print" and "blocked" in why for n, why in out.skipped)


def test_headline_saving(res):
    assert res.savings_monthly == 318.09
