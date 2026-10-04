"""List-price cost model: what one resource costs per month (730 h) at snapshot list prices.

Used in two places: to synthesize the FOCUS cost export, and by each pattern to price the
"before" and "after" of a recommendation, so both sides use one model.
"""

from __future__ import annotations

from typing import Any

from finops import HOURS_PER_MONTH, SECONDS_PER_MONTH
from finops.pricing import PriceBook, default_book, vm_key

VM_SHAPES = {  # size: (vCPU, GiB)
    "D2s_v5": (2, 8),
    "D4s_v5": (4, 16),
    "D8s_v5": (8, 32),
    "E4s_v5": (4, 32),
}
WS_SHAPES = {"WS1": (1, 3.5), "WS2": (2, 7.0), "WS3": (4, 14.0)}
EP_SHAPES = {"EP1": (1, 3.5), "EP2": (2, 7.0), "EP3": (4, 14.0)}


def sql_license_key(edition: str, vcpu: int) -> str:
    """SQL Server pay-as-you-go license meter for a VM of ``vcpu`` cores (1-4 share one meter)."""
    return f"license.sql_{edition}.{4 if vcpu <= 4 else 8}vcpu_hour"


def logic_apps_standard_hourly(sku: str, book: PriceBook | None = None) -> float:
    book = book or default_book()
    vcpu, gib = WS_SHAPES[sku]
    return vcpu * book.price("logicapps.standard.vcpu_hour") + gib * book.price("logicapps.standard.gib_hour")


def functions_premium_hourly(sku: str, book: PriceBook | None = None) -> float:
    book = book or default_book()
    vcpu, gib = EP_SHAPES[sku]
    return vcpu * book.price("functions.premium.vcpu_hour") + gib * book.price("functions.premium.gib_hour")


def container_app_monthly(
    min_replicas: int,
    vcpu: float,
    gib: float,
    active_fraction: float,
    monthly_requests: int,
    book: PriceBook | None = None,
) -> float:
    """Consumption-profile Container App. A warm replica bills the idle rate whenever it is not
    serving, and the active rate while serving. The per-subscription monthly free grant is ignored
    (conservative: real bills for tiny apps are lower)."""
    book = book or default_book()
    active_s = SECONDS_PER_MONTH * active_fraction * max(min_replicas, 1 if active_fraction else 0)
    idle_s = SECONDS_PER_MONTH * (1 - active_fraction) * min_replicas
    active = active_s * (
        vcpu * book.price("containerapps.vcpu_active_second")
        + gib * book.price("containerapps.gib_active_second")
    )
    idle = idle_s * (
        vcpu * book.price("containerapps.vcpu_idle_second")
        + gib * book.price("containerapps.gib_idle_second")
    )
    reqs = monthly_requests / 1e6 * book.price("containerapps.requests_million")
    return active + idle + reqs


def monthly_cost(r: dict[str, Any], book: PriceBook | None = None) -> float:
    """List cost of one inventory record for a 730-hour month. Unknown or free types cost 0."""
    book = book or default_book()
    t, sku, p = r["type"], r["sku"], r["properties"]
    if t.endswith("virtualMachines"):
        if p.get("power_state") == "deallocated":
            return 0.0  # deallocated VMs bill disks only (disks are not modelled per VM)
        cost = book.monthly(vm_key(sku, p.get("os", "linux")))
        if p.get("sql_edition") and p.get("sql_license") != "ahb":
            cost += book.monthly(sql_license_key(p["sql_edition"], VM_SHAPES[sku][0]))
        return cost
    if t.endswith("managedClusters"):
        return book.monthly(vm_key(sku)) * p["node_count"]
    if t.endswith("serverfarms"):
        if sku in WS_SHAPES:
            return logic_apps_standard_hourly(sku, book) * HOURS_PER_MONTH
        return book.monthly(f"appservice.{sku}") * p.get("instances", 1)
    if t.endswith("sites"):
        if p.get("plan"):
            return 0.0  # billed on its plan
        if sku in WS_SHAPES:
            return logic_apps_standard_hourly(sku, book) * HOURS_PER_MONTH
        if sku in EP_SHAPES:
            return functions_premium_hourly(sku, book) * HOURS_PER_MONTH
        return 0.0
    if t.endswith("containerApps"):
        return container_app_monthly(
            p["min_replicas"], p["vcpu"], p["gib"], p["active_fraction"], p["monthly_requests"], book
        )
    if t.endswith("disks"):
        return book.monthly(f"disk.{sku}")
    if t.endswith("publicIPAddresses"):
        return book.monthly("publicip.standard_static_hour")
    if t.endswith("workspaces"):
        gb = p["ingest_gb_per_day"] * 30
        return book.tiered_cost("loganalytics.analytics_ingest_gb", gb)
    return 0.0
