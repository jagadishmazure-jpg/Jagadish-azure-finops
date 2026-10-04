import pytest

from finops.datasets import load_compute_usage
from finops.patterns import p03_commitments as P


@pytest.fixture(scope="module")
def res():
    return P.analyze()


def test_brute_force_matches_analytic_level(res):
    for row in res.extra["options"]:
        assert row["level"] == row["analytic_level"]


def test_commit_never_exceeds_minimum_for_one_year_ri(res):
    pick = res.findings[0].evidence["pick"]
    assert pick["option"] == "reservation-1y" and pick["level"] == 13 == res.extra["usage_min"]


def test_breakeven_utilization_equals_rate_ratio(book):
    usage = load_compute_usage()
    payg = book.price("vm.D2s_v5.linux.payg")
    rate = book.reservation_hourly("vm.D2s_v5.linux.ri1y")
    assert P.cost_at(usage, 0, rate, payg) > P.best_level(usage, rate, payg)[1]


def test_breakeven_months():
    assert P.breakeven_months(0.5, 1.0, 1) == 6.0


def test_three_year_terms_allowed_only_by_policy():
    assert P.analyze(max_term_years=3).findings[0].evidence["pick"]["option"] == "reservation-3y"


def test_purchase_is_marked_irreversible(res):
    assert res.findings[0].reversible is False


def test_headline_saving(res):
    assert res.savings_monthly == 348.79
