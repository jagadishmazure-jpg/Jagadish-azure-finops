import pytest
from tests.conftest import find

from finops.patterns import p10_cache_egress as P


@pytest.fixture(scope="module")
def res():
    return P.analyze()


def test_incremental_copy_is_the_big_lever(res):
    f = find(res, "nightly-lake-copy")
    assert f.savings_monthly == pytest.approx(739.2) and f.evidence["gb_incremental"] == 5040


def test_redis_pays_for_itself(res):
    f = find(res, "tracking-api")
    assert f.change["origin_instances"] == 2 and f.savings_monthly > 0


def test_front_door_priced_with_base_fee(book):
    assert P.front_door_monthly(0, 0) == book.price("frontdoor.standard.base_month")


def test_front_door_rejected_when_not_cheaper(monkeypatch):
    reg = {
        "endpoints": [
            {
                "name": "tiny",
                "origin": "stlkportalassets",
                "egress_gb": 150,
                "requests_10k": 10,
                "cacheable": 0.9,
                "expected_hit_ratio": 0.8,
                "origin_plan": None,
            }
        ],
        "cross_region": [],
    }
    monkeypatch.setattr(P, "load_json", lambda _: reg)
    out = P.analyze()
    assert not out.findings and "would not beat" in out.skipped[0][1]


def test_all_cache_findings_are_estimates(res):
    assert all(f.estimate for f in res.findings)


def test_headline_saving(res):
    assert res.savings_monthly == 930.38
