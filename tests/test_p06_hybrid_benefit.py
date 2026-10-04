import pytest

from finops.patterns import p06_hybrid_benefit as P


@pytest.fixture(scope="module")
def res():
    return P.analyze()


def test_core_rules():
    assert P.windows_cores(2) == 8 and P.windows_cores(16) == 16
    assert P.sql_cores(2) == 4 and P.sql_cores(8) == 8


def test_greedy_assignment_respects_pool():
    cands = [{"name": "a", "cores": 8, "saving": 100}, {"name": "b", "cores": 8, "saving": 50}, {"name": "c", "cores": 8, "saving": 80}]
    covered, left = P.assign(cands, 16)
    assert [c["name"] for c in covered] == ["a", "c"] and [c["name"] for c in left] == ["b"]


def test_pool_exhaustion_is_reported(res):
    assert any(n == "vm-jump-01" and "no Windows Server cores" in why for n, why in res.skipped)


def test_assessed_after_rightsizing(res):
    f = next(f for f in res.findings if f.resource_name == "vm-dispatch-legacy-01")
    assert f.evidence["size_assessed"] == "D2s_v5"


def test_sql_license_drops_to_zero(res):
    f = next(f for f in res.findings if "SQL" in f.action)
    assert f.proposed_monthly == 0 and f.savings_monthly == 292.0


def test_headline_saving(res):
    assert res.savings_monthly == 493.48
