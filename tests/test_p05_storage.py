import pytest

from finops.patterns import p05_storage_tiering as P
from tests.conftest import find


@pytest.fixture(scope="module")
def res():
    return P.analyze()


def test_legal_hold_is_excluded(res):
    assert any(n == "audit-archive" for n, _ in res.skipped)


def test_read_heavy_container_stays_hot(res):
    assert any(n == "ml-features" for n, _ in res.skipped)


def test_short_rto_rules_out_archive(res):
    assert "archive" not in find(res, "stlkdatalake/shipment-docs").action


def test_min_retention_is_respected():
    tier, costs = P.choose_tier({"min_age": 30, "gb": 1000, "read_gb": 0}, 48)
    assert "cold" not in costs and "archive" not in costs and tier == "cool"


def test_policy_uses_earliest_age_per_tier(res):
    rules = {r["name"]: r for r in res.extra["policy"]["policy"]["rules"]}
    docs = rules["tier-shipment-docs"]["definition"]["actions"]["baseBlob"]
    assert docs["tierToCold"]["daysAfterLastAccessTimeGreaterThan"] == 90
    assert docs["enableAutoTierToHotFromCool"] is True


def test_policy_is_valid_management_policy_shape(res):
    for r in res.extra["policy"]["policy"]["rules"]:
        assert r["type"] == "Lifecycle" and r["definition"]["filters"]["blobTypes"] == ["blockBlob"]


def test_archive_cheapest_for_cold_unread_data():
    tier, _ = P.choose_tier({"min_age": 180, "gb": 1000, "read_gb": 0}, 48)
    assert tier == "archive"


def test_headline_saving(res):
    assert res.savings_monthly == 1844.01
