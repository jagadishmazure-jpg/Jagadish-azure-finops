"""The list-price snapshot and the PriceBook that reads it."""

import json

import pytest

from finops.pricing import SNAPSHOT, PriceBook, UnknownMeter, vm_key


def test_snapshot_is_labelled_as_list_prices():
    doc = json.loads(SNAPSHOT.read_text())
    assert doc["label"].startswith("LIST-PRICE SNAPSHOT")
    assert doc["source"] == "https://prices.azure.com/api/retail/prices"


def test_snapshot_has_no_dates_or_ids():
    text = SNAPSHOT.read_text()
    assert "effectiveStartDate" not in text and "meterId" not in text


def test_snapshot_is_sorted_and_unique():
    keys = [i["key"] for i in json.loads(SNAPSHOT.read_text())["items"]]
    assert keys == sorted(keys) and len(keys) == len(set(keys))


def test_known_list_prices(book):
    assert book.price("vm.D4s_v5.linux.payg") == 0.192
    assert book.price("vm.D4s_v5.windows.payg") == 0.376
    assert book.price("logicapps.standard.vcpu_hour") == 0.192
    assert book.price("logicapps.standard.gib_hour") == 0.0137


def test_monthly_uses_730_hours(book):
    assert book.monthly("vm.D4s_v5.linux.payg") == pytest.approx(140.16)


def test_monthly_meter_is_not_multiplied(book):
    assert book.monthly("disk.P30") == 122.88


def test_reservation_total_is_spread_over_term(book):
    assert book.reservation_hourly("vm.D2s_v5.linux.ri1y") == pytest.approx(519 / 8760)
    assert book.reservation_hourly("vm.D2s_v5.linux.ri3y") == pytest.approx(997 / 26280)


def test_reservations_are_cheaper_than_payg(book):
    for size in ("D2s_v5", "D4s_v5", "D8s_v5", "E4s_v5"):
        payg = book.price(vm_key(size))
        assert (
            book.reservation_hourly(vm_key(size, offer="ri3y"))
            < book.reservation_hourly(vm_key(size, offer="ri1y"))
            < payg
        )


def test_savings_plan_prices(book):
    assert book.savings_plan_hourly("vm.D2s_v5.linux.payg", "1 Year") == 0.06624
    with pytest.raises(UnknownMeter):
        book.savings_plan_hourly("disk.P30", "1 Year")


def test_tiered_cost_walks_tiers(book):
    # first 100 GB of internet egress are free in the snapshot
    assert book.tiered_cost("bandwidth.internet_egress_gb", 100) == 0
    assert book.tiered_cost("bandwidth.internet_egress_gb", 200) == pytest.approx(100 * 0.087)


def test_unit_price_skips_free_tier(book):
    assert book.price("functions.flex.ondemand_gb_second") == 2.6e-05


def test_unknown_meter_raises(book):
    with pytest.raises(UnknownMeter):
        book.price("vm.nope")


def test_hourly_only_for_hour_or_month_meters(book):
    with pytest.raises(ValueError):
        book.monthly("blob.hot.read_10k")


def test_spot_is_cheapest_vm_offer(book):
    assert book.price(vm_key("D8s_v5", offer="spot")) < book.price(vm_key("D8s_v5")) * 0.5


def test_pricebook_reads_a_custom_file(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(
        json.dumps(
            {
                "label": "x",
                "region": "r",
                "items": [
                    {
                        "key": "k",
                        "serviceName": "s",
                        "productName": "p",
                        "meterName": "m",
                        "unitOfMeasure": "1 Hour",
                        "tiers": [{"from_units": 0, "price": 2.0}],
                    }
                ],
            }
        )
    )
    assert PriceBook(p).monthly("k") == 1460
