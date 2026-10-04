"""Read-only access to the checked-in Azure Retail Prices LIST-PRICE SNAPSHOT.

Every scenario prices resources through :class:`PriceBook`, never through hard-coded numbers, so
one refresh of the snapshot (``scripts/refresh_prices.py``) re-prices the whole repo.

Two quirks of the Retail Prices API are handled here:

* Reservation meters report the *total* upfront price for the term even though their
  ``unitOfMeasure`` says "1 Hour". :meth:`PriceBook.reservation_hourly` spreads it over the term.
* Some meters are tiered (``tierMinimumUnits``). :meth:`PriceBook.tiered_cost` walks the tiers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from finops import DATA, HOURS_PER_MONTH

SNAPSHOT = DATA / "pricing" / "retail-prices-snapshot.json"
HOURS_PER_YEAR = 8760


class UnknownMeter(KeyError):
    pass


@dataclass(frozen=True)
class Meter:
    key: str
    service: str
    product: str
    meter: str
    unit: str
    tiers: tuple[tuple[float, float], ...]  # (from_units, unit_price)
    savings_plan: dict[str, float]
    reservation_term: str = ""

    @property
    def unit_price(self) -> float:
        """Price of the first tier that is not free (the marginal list price)."""
        for _, price in self.tiers:
            if price > 0:
                return price
        return 0.0


class PriceBook:
    def __init__(self, path: Path = SNAPSHOT):
        doc = json.loads(path.read_text())
        self.label: str = doc["label"]
        self.region: str = doc["region"]
        self._meters: dict[str, Meter] = {}
        for item in doc["items"]:
            self._meters[item["key"]] = Meter(
                key=item["key"],
                service=item["serviceName"],
                product=item["productName"],
                meter=item["meterName"],
                unit=item["unitOfMeasure"],
                tiers=tuple((t["from_units"], t["price"]) for t in item["tiers"]),
                savings_plan=dict(item.get("savingsPlan", {})),
                reservation_term=item.get("reservationTerm", ""),
            )

    def __contains__(self, key: str) -> bool:
        return key in self._meters

    def keys(self) -> list[str]:
        return sorted(self._meters)

    def meter(self, key: str) -> Meter:
        try:
            return self._meters[key]
        except KeyError as exc:
            raise UnknownMeter(key) from exc

    def price(self, key: str) -> float:
        """Marginal unit price (first non-free tier)."""
        return self.meter(key).unit_price

    def monthly(self, key: str, quantity: float = 1.0) -> float:
        """Monthly cost of an hourly meter running 730 hours (or a monthly meter as-is)."""
        m = self.meter(key)
        if "Month" in m.unit:
            return m.unit_price * quantity
        if "Hour" in m.unit:
            return m.unit_price * HOURS_PER_MONTH * quantity
        raise ValueError(f"{key} is billed per {m.unit}, not per hour or month")

    def tiered_cost(self, key: str, units: float) -> float:
        """Cost of ``units`` on a tiered meter (units in the meter's own unit of measure)."""
        tiers = self.meter(key).tiers
        total = 0.0
        for i, (start, price) in enumerate(tiers):
            end = tiers[i + 1][0] if i + 1 < len(tiers) else float("inf")
            if units <= start:
                break
            total += (min(units, end) - start) * price
        return total

    def reservation_hourly(self, key: str) -> float:
        """Effective hourly rate of a reservation (total term price / hours in the term)."""
        m = self.meter(key)
        years = {"1 Year": 1, "3 Years": 3}[m.reservation_term]
        return m.unit_price / (HOURS_PER_YEAR * years)

    def savings_plan_hourly(self, payg_key: str, term: str) -> float:
        m = self.meter(payg_key)
        if term not in m.savings_plan:
            raise UnknownMeter(f"{payg_key} has no {term} savings plan price")
        return m.savings_plan[term]


@cache
def default_book() -> PriceBook:
    return PriceBook()


def vm_key(size: str, os: str = "linux", offer: str = "payg") -> str:
    return f"vm.{size}.{os}.{offer}"
