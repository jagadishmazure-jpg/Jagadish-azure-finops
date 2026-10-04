"""Capture the Azure Retail Prices list-price snapshot used by every scenario.

The Retail Prices API (https://prices.azure.com/api/retail/prices) is public and needs no sign-in.
This script asks it for the handful of meters the scenarios use and writes them, sorted, to
``data/pricing/retail-prices-snapshot.json``. The scenarios and tests only ever read that file, so
the repo stays offline and every number is reproducible.

These are LIST prices (pay-as-you-go retail, USD, no EA/MCA discounts, no negotiated rates). Your
invoice will differ. Re-run this script to refresh the snapshot; tests pin the values they use, so
a price change shows up as a failing test you then review.

    python scripts/refresh_prices.py            # rewrite the snapshot
    python scripts/refresh_prices.py --check    # exit 1 if the live API differs from the snapshot
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://prices.azure.com/api/retail/prices"
API_VERSION = "2023-01-01-preview"  # this version returns the savingsPlan block
OUT = Path(__file__).resolve().parents[1] / "data" / "pricing" / "retail-prices-snapshot.json"
REGION = "eastus2"
KEEP = (
    "serviceName",
    "productName",
    "skuName",
    "meterName",
    "armRegionName",
    "type",
    "reservationTerm",
    "unitOfMeasure",
    "retailPrice",
    "tierMinimumUnits",
)


def vm(size: str, series: str) -> list[tuple]:
    base = f"armRegionName eq '{REGION}' and armSkuName eq 'Standard_{size}'"
    meter = size.replace("_v5", " v5")
    return [
        (
            f"vm.{size}.linux.payg",
            base,
            {"productName": f"Virtual Machines {series} Series", "meterName": meter, "type": "Consumption"},
            "single",
        ),
        (
            f"vm.{size}.windows.payg",
            base,
            {
                "productName": f"Virtual Machines {series} Series Windows",
                "meterName": meter,
                "type": "Consumption",
            },
            "single",
        ),
        (
            f"vm.{size}.linux.spot",
            base,
            {
                "productName": f"Virtual Machines {series} Series",
                "meterName": f"{meter} Spot",
                "type": "Consumption",
            },
            "single",
        ),
        (
            f"vm.{size}.linux.ri1y",
            base,
            {
                "productName": f"Virtual Machines {series} Series",
                "meterName": meter,
                "type": "Reservation",
                "reservationTerm": "1 Year",
            },
            "single",
        ),
        (
            f"vm.{size}.linux.ri3y",
            base,
            {
                "productName": f"Virtual Machines {series} Series",
                "meterName": meter,
                "type": "Reservation",
                "reservationTerm": "3 Years",
            },
            "single",
        ),
    ]


R = f"armRegionName eq '{REGION}'"
SPECS: list[tuple] = [
    *vm("D2s_v5", "Dsv5"),
    *vm("D4s_v5", "Dsv5"),
    *vm("D8s_v5", "Dsv5"),
    *vm("E4s_v5", "Esv5"),
    # App Service (Linux)
    *[
        (
            f"appservice.{k}",
            f"{R} and serviceName eq 'Azure App Service' and productName eq '{p}'",
            {"meterName": m, "type": "Consumption"},
            "single",
        )
        for k, p, m in [
            ("B1", "Azure App Service Basic Plan - Linux", "B1"),
            ("P0v3", "Azure App Service Premium v3 Plan - Linux", "P0v3 App"),
            ("P1v3", "Azure App Service Premium v3 Plan - Linux", "P1 v3 App"),
            ("P2v3", "Azure App Service Premium v3 Plan - Linux", "P2 v3 App"),
            ("P3v3", "Azure App Service Premium v3 Plan - Linux", "P3 v3 App"),
        ]
    ],
    # Logic Apps Standard (WS plans bill vCPU + memory duration)
    (
        "logicapps.standard.vcpu_hour",
        f"{R} and serviceName eq 'Logic Apps'",
        {"meterName": "Standard vCPU Duration", "type": "Consumption"},
        "single",
    ),
    (
        "logicapps.standard.gib_hour",
        f"{R} and serviceName eq 'Logic Apps'",
        {"meterName": "Standard Memory Duration", "type": "Consumption"},
        "single",
    ),
    (
        "logicapps.consumption.standard_action",
        f"{R} and serviceName eq 'Logic Apps'",
        {"meterName": "Consumption Standard Connector Actions", "type": "Consumption"},
        "single",
    ),
    # Container Apps (consumption profile)
    *[
        (
            f"containerapps.{k}",
            f"{R} and serviceName eq 'Azure Container Apps'",
            {"meterName": m, "type": "Consumption"},
            "single",
        )
        for k, m in [
            ("vcpu_active_second", "Standard vCPU Active Usage"),
            ("vcpu_idle_second", "Standard vCPU Idle Usage"),
            ("gib_active_second", "Standard Memory Active Usage"),
            ("gib_idle_second", "Standard Memory Idle Usage"),
            ("requests_million", "Standard Requests"),
        ]
    ],
    # Functions
    (
        "functions.flex.ondemand_gb_second",
        f"{R} and serviceName eq 'Functions' and productName eq 'Flex Consumption'",
        {"meterName": "On Demand Execution Time", "type": "Consumption"},
        "tiers",
    ),
    (
        "functions.flex.ondemand_executions_10",
        f"{R} and serviceName eq 'Functions' and productName eq 'Flex Consumption'",
        {"meterName": "On Demand Total Executions", "type": "Consumption"},
        "tiers",
    ),
    (
        "functions.premium.vcpu_hour",
        f"{R} and serviceName eq 'Functions' and productName eq 'Premium Functions'",
        {"meterName": "Premium vCPU Duration", "type": "Consumption"},
        "single",
    ),
    (
        "functions.premium.gib_hour",
        f"{R} and serviceName eq 'Functions' and productName eq 'Premium Functions'",
        {"meterName": "Premium Memory Duration", "type": "Consumption"},
        "single",
    ),
    # Blob storage (LRS, General Purpose v2)
    *[
        (
            f"blob.{t.lower()}.{k}",
            f"{R} and serviceName eq 'Storage' and productName eq 'General Block Blob v2' and skuName eq '{t} LRS'",
            {"meterName": m.format(t=t), "type": "Consumption"},
            mode,
        )
        for t in ("Hot", "Cool", "Cold", "Archive")
        for k, m, mode in [("gb_month", "{t} LRS Data Stored", "tiers")]
    ],
    (
        "blob.hot.read_10k",
        f"{R} and serviceName eq 'Storage' and productName eq 'General Block Blob v2' and skuName eq 'Hot LRS'",
        {"meterName": "Hot Read Operations", "type": "Consumption"},
        "single",
    ),
    (
        "blob.cool.read_10k",
        f"{R} and serviceName eq 'Storage' and productName eq 'General Block Blob v2' and skuName eq 'Cool LRS'",
        {"meterName": "Cool Read Operations", "type": "Consumption"},
        "single",
    ),
    (
        "blob.cold.read_10k",
        f"{R} and serviceName eq 'Storage' and productName eq 'General Block Blob v2' and skuName eq 'Cold LRS'",
        {"meterName": "Cold LRS Read Operations", "type": "Consumption"},
        "single",
    ),
    (
        "blob.archive.read_10k",
        f"{R} and serviceName eq 'Storage' and productName eq 'General Block Blob v2' and skuName eq 'Archive LRS'",
        {"meterName": "Archive Read Operations", "type": "Consumption"},
        "single",
    ),
    (
        "blob.cool.retrieval_gb",
        f"{R} and serviceName eq 'Storage' and productName eq 'General Block Blob v2' and skuName eq 'Cool LRS'",
        {"meterName": "Cool Data Retrieval", "type": "Consumption"},
        "single",
    ),
    (
        "blob.cold.retrieval_gb",
        f"{R} and serviceName eq 'Storage' and productName eq 'General Block Blob v2' and skuName eq 'Cold LRS'",
        {"meterName": "Cold LRS Data Retrieval", "type": "Consumption"},
        "single",
    ),
    (
        "blob.archive.retrieval_gb",
        f"{R} and serviceName eq 'Storage' and productName eq 'General Block Blob v2' and skuName eq 'Archive LRS'",
        {"meterName": "Archive Data Retrieval", "type": "Consumption"},
        "single",
    ),
    (
        "blob.cool.write_10k",
        f"{R} and serviceName eq 'Storage' and productName eq 'General Block Blob v2' and skuName eq 'Cool LRS'",
        {"meterName": "Cool LRS Write Operations", "type": "Consumption"},
        "single",
    ),
    (
        "blob.cold.write_10k",
        f"{R} and serviceName eq 'Storage' and productName eq 'General Block Blob v2' and skuName eq 'Cold LRS'",
        {"meterName": "Cold LRS Write Operations", "type": "Consumption"},
        "single",
    ),
    (
        "blob.archive.write_10k",
        f"{R} and serviceName eq 'Storage' and productName eq 'General Block Blob v2' and skuName eq 'Archive LRS'",
        {"meterName": "Archive LRS Write Operations", "type": "Consumption"},
        "single",
    ),
    # Managed disks
    *[
        (
            f"disk.{d}",
            f"{R} and serviceName eq 'Storage' and productName eq '{p}' and skuName eq '{d} LRS'",
            {"meterName": f"{d} LRS Disk", "type": "Consumption"},
            "single",
        )
        for d, p in [
            ("P10", "Premium SSD Managed Disks"),
            ("P30", "Premium SSD Managed Disks"),
            ("E10", "Standard SSD Managed Disks"),
            ("E30", "Standard SSD Managed Disks"),
        ]
    ],
    # Public IP
    (
        "publicip.standard_static_hour",
        f"{R} and serviceName eq 'Virtual Network' and productName eq 'IP Addresses'",
        {"meterName": "Standard IPv4 Static Public IP", "type": "Consumption"},
        "single",
    ),
    # Redis
    (
        "redis.basic.C0",
        f"{R} and serviceName eq 'Redis Cache' and productName eq 'Azure Redis Cache Basic'",
        {"meterName": "C0 Cache", "type": "Consumption"},
        "single",
    ),
    (
        "redis.basic.C1",
        f"{R} and serviceName eq 'Redis Cache' and productName eq 'Azure Redis Cache Basic'",
        {"meterName": "C1 Cache", "type": "Consumption"},
        "single",
    ),
    (
        "redis.standard.C1",
        f"{R} and serviceName eq 'Redis Cache' and productName eq 'Azure Redis Cache Standard'",
        {"meterName": "C1 Cache", "type": "Consumption"},
        "single",
    ),
    # Data transfer
    (
        "bandwidth.internet_egress_gb",
        f"{R} and serviceName eq 'Bandwidth' and productName eq 'Rtn Preference: MGN'",
        {"meterName": "Standard Data Transfer Out", "type": "Consumption"},
        "tiers",
    ),
    (
        "bandwidth.inter_region_gb",
        f"{R} and serviceName eq 'Bandwidth' and productName eq 'Rtn Preference: MGN'",
        {"meterName": "Standard Inter-Region Data Transfer", "type": "Consumption"},
        "single",
    ),
    (
        "frontdoor.standard.base_month",
        "serviceName eq 'Azure Front Door Service' and productName eq 'Azure Front Door' and armRegionName eq 'Zone 1'",
        {"meterName": "Standard Base Fees", "type": "Consumption"},
        "single",
    ),
    (
        "frontdoor.standard.egress_gb",
        "serviceName eq 'Azure Front Door Service' and productName eq 'Azure Front Door' and armRegionName eq 'Zone 1'",
        {"meterName": "Standard Data Transfer Out", "type": "Consumption"},
        "tiers",
    ),
    (
        "frontdoor.standard.requests_10k",
        "serviceName eq 'Azure Front Door Service' and productName eq 'Azure Front Door' and armRegionName eq 'Zone 1'",
        {"meterName": "Standard Requests", "type": "Consumption"},
        "tiers",
    ),
    # Log Analytics
    (
        "loganalytics.analytics_ingest_gb",
        f"{R} and serviceName eq 'Log Analytics'",
        {"meterName": "Analytics Logs Data Ingestion", "type": "Consumption"},
        "tiers",
    ),
    # Azure OpenAI (Foundry Models), global deployments
    *[
        (
            f"aoai.{k}",
            f"{R} and serviceName eq 'Foundry Models' and productName eq 'Azure OpenAI'",
            {"meterName": m, "type": "Consumption"},
            "single",
        )
        for k, m in [
            ("gpt-4o.input_1k", "gpt 4o 1120 Inp glbl Tokens"),
            ("gpt-4o.cached_input_1k", "gpt 4o 1120 cached Inp glbl Tokens"),
            ("gpt-4o.output_1k", "gpt 4o 1120 Outp glbl Tokens"),
            ("gpt-4o-mini.input_1k", "gpt-4o-mini-0718-Inp-glbl Tokens"),
            ("gpt-4o-mini.output_1k", "gpt-4o-mini-0718-Outp-glbl Tokens"),
            ("ptu.global_hour", "Provisioned Managed Global Unit"),
        ]
    ],
    # SQL Server licenses on VMs (used for Azure Hybrid Benefit)
    *[
        (
            f"license.sql_{ed.lower()}.{k}vcpu_hour",
            f"serviceName eq 'Virtual Machines Licenses' and productName eq 'SQL Server {ed}'",
            {"meterName": f"{n} vCPU VM License", "type": "Consumption"},
            "single",
        )
        for ed in ("Standard", "Enterprise")
        for k, n in (("4", "1-4"), ("8", "8"))
    ],
]


def fetch(flt: str) -> list[dict]:
    url = f"{API}?api-version={API_VERSION}&$filter={urllib.parse.quote(flt)}"
    items: list[dict] = []
    while url:
        for attempt in range(8):
            try:
                with urllib.request.urlopen(url, timeout=60) as r:
                    page = json.load(r)
                break
            except urllib.error.HTTPError as exc:  # 429: the API rate-limits bursts
                if exc.code != 429 or attempt == 7:
                    raise
                time.sleep(2 * (attempt + 1))
        items += page["Items"]
        url = page.get("NextPageLink")
    return items


def build() -> list[dict]:
    cache: dict[str, list[dict]] = {}
    out = []
    for key, flt, match, mode in SPECS:
        if flt not in cache:
            cache[flt] = fetch(flt)
        hits = [i for i in cache[flt] if all(i.get(k) == v for k, v in match.items())]
        if mode == "single":
            # the API sometimes repeats a meter (e.g. a second location label); same price either way
            prices = {i["retailPrice"] for i in hits if i.get("tierMinimumUnits", 0) == 0}
            if len(prices) != 1:
                raise SystemExit(f"{key}: expected one price, got {sorted(prices)} from {len(hits)} items")
            hits = [next(i for i in hits if i.get("tierMinimumUnits", 0) == 0)]
        else:
            seen: dict[float, dict] = {}
            for i in hits:
                seen.setdefault(i["tierMinimumUnits"], i)
            hits = [seen[t] for t in sorted(seen)]
            if not hits:
                raise SystemExit(f"{key}: no items")
        tiers = [{"from_units": i["tierMinimumUnits"], "price": i["retailPrice"]} for i in hits]
        first = {k: hits[0].get(k, "") for k in KEEP if k not in ("retailPrice", "tierMinimumUnits")}
        sp = {s["term"]: s["retailPrice"] for s in hits[0].get("savingsPlan") or []}
        out.append(
            {"key": key, **first, "tiers": tiers, **({"savingsPlan": dict(sorted(sp.items()))} if sp else {})}
        )
    return sorted(out, key=lambda e: e["key"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    doc = {
        "label": "LIST-PRICE SNAPSHOT: Azure Retail Prices API, pay-as-you-go USD list prices. Not an invoice; excludes EA/MCA/CSP discounts.",
        "source": API,
        "api_version": API_VERSION,
        "region": REGION,
        "items": build(),
    }
    text = json.dumps(doc, indent=1, sort_keys=False) + "\n"
    if a.check:
        same = OUT.exists() and OUT.read_text() == text
        print(
            "snapshot matches the live API"
            if same
            else "snapshot differs from the live API; review and refresh"
        )
        return 0 if same else 1
    OUT.write_text(text)
    print(f"wrote {len(doc['items'])} meters to {OUT.relative_to(OUT.parents[2])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
