"""Synthesize and read a FOCUS-format cost export.

FOCUS (FinOps Open Cost and Usage Specification) is the vendor-neutral billing schema that Azure
Cost Management can export. The export here uses a subset of the FOCUS 1.0 columns, one row per
resource per day for a 30-day synthetic billing period, priced at snapshot list prices.

The period dates are synthetic placeholders; nothing here comes from a real bill.
"""

from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from finops import HOURS_PER_MONTH
from finops import synth as S
from finops.costing import monthly_cost
from finops.pricing import PriceBook, default_book, vm_key

COLUMNS = [
    "BillingAccountId",
    "BillingCurrency",
    "BillingPeriodStart",
    "BillingPeriodEnd",
    "ChargePeriodStart",
    "ChargePeriodEnd",
    "ChargeCategory",
    "ChargeDescription",
    "SubAccountId",
    "SubAccountName",
    "ResourceId",
    "ResourceName",
    "ResourceType",
    "RegionId",
    "ServiceCategory",
    "ServiceName",
    "SkuId",
    "PricingCategory",
    "PricingQuantity",
    "PricingUnit",
    "ListUnitPrice",
    "ListCost",
    "ContractedCost",
    "BilledCost",
    "EffectiveCost",
    "ConsumedQuantity",
    "ConsumedUnit",
    "CommitmentDiscountId",
    "Tags",
]
PERIOD_START = "2030-01-01T00:00:00Z"  # synthetic placeholder period
PERIOD_END = "2030-01-31T00:00:00Z"

SERVICE = {
    "Microsoft.Compute/virtualMachines": ("Compute", "Virtual Machines"),
    "Microsoft.ContainerService/managedClusters": ("Compute", "Azure Kubernetes Service"),
    "Microsoft.Web/serverfarms": ("Compute", "Azure App Service"),
    "Microsoft.Web/sites": ("Compute", "Azure App Service"),
    "Microsoft.App/containerApps": ("Compute", "Azure Container Apps"),
    "Microsoft.Compute/disks": ("Storage", "Storage"),
    "Microsoft.Network/publicIPAddresses": ("Networking", "Virtual Network"),
    "Microsoft.Network/networkInterfaces": ("Networking", "Virtual Network"),
    "Microsoft.Storage/storageAccounts": ("Storage", "Storage"),
    "Microsoft.OperationalInsights/workspaces": ("Management and Governance", "Log Analytics"),
    "Microsoft.Batch/batchAccounts": ("Compute", "Batch"),
    "Microsoft.CognitiveServices/accounts": ("AI and Machine Learning", "Foundry Models"),
}


def _day(d: int) -> tuple[str, str]:
    return f"2030-01-{d:02d}T00:00:00Z", (f"2030-01-{d + 1:02d}T00:00:00Z" if d < 31 else PERIOD_END)


def _row(
    r: dict[str, Any], day: int, cost: float, qty: float, unit: str, sku: str, desc: str, unit_price: float
) -> dict[str, Any]:
    start, end = _day(day)
    cat, svc = SERVICE.get(r["type"], ("Other", "Other"))
    c = round(cost, 6)
    return {
        "BillingAccountId": "ba-larkspur-freight",
        "BillingCurrency": "USD",
        "BillingPeriodStart": PERIOD_START,
        "BillingPeriodEnd": PERIOD_END,
        "ChargePeriodStart": start,
        "ChargePeriodEnd": end,
        "ChargeCategory": "Usage",
        "ChargeDescription": desc,
        "SubAccountId": r["subscription"],
        "SubAccountName": r["subscription"],
        "ResourceId": r["id"],
        "ResourceName": r["name"],
        "ResourceType": r["type"],
        "RegionId": r["location"],
        "ServiceCategory": cat,
        "ServiceName": svc,
        "SkuId": sku,
        "PricingCategory": "Standard",
        "PricingQuantity": round(qty, 6),
        "PricingUnit": unit,
        "ListUnitPrice": unit_price,
        "ListCost": c,
        "ContractedCost": c,
        "BilledCost": c,
        "EffectiveCost": c,
        "ConsumedQuantity": round(qty, 6),
        "ConsumedUnit": unit,
        "CommitmentDiscountId": "",
        "Tags": json.dumps(r["tags"], sort_keys=True),
    }


def _batch_days(runs: int) -> list[int]:
    if runs >= S.DAYS:
        return list(range(1, S.DAYS + 1))
    if runs == 1:
        return [S.DAYS]
    step = S.DAYS / runs
    return [int(i * step) + 1 for i in range(runs)]


def generate(book: PriceBook | None = None) -> list[dict[str, Any]]:
    book = book or default_book()
    inv = S.inventory()
    by_name = {r["name"]: r for r in inv}
    rows: list[dict[str, Any]] = []
    for r in inv:
        t = r["type"]
        if t.endswith("accounts") or t.endswith("Accounts"):
            continue  # priced below from their own datasets
        monthly = monthly_cost(r, book)
        if monthly == 0 and not t.endswith("networkInterfaces"):
            continue
        hourly = monthly / HOURS_PER_MONTH
        for d in range(1, S.DAYS + 1):
            rows.append(
                _row(
                    r,
                    d,
                    hourly * 24,
                    24,
                    "Hours",
                    f"{t.split('/')[-1]}:{r['sku']}",
                    f"{r['sku']} usage",
                    round(hourly, 6),
                )
            )
    # storage accounts: everything is in the Hot tier today
    hot = book.price("blob.hot.gb_month")
    for acct in {c["account"] for c in S.storage_containers()}:
        r = by_name[acct]
        gb = sum(b["gb"] for c in S.storage_containers() if c["account"] == acct for b in c["buckets"])
        monthly = book.tiered_cost("blob.hot.gb_month", gb)
        for d in range(1, S.DAYS + 1):
            rows.append(
                _row(
                    r,
                    d,
                    monthly / S.DAYS,
                    gb / S.DAYS,
                    "GB-Month",
                    "blob.hot.gb_month",
                    "Hot LRS data stored",
                    hot,
                )
            )
    # egress from the portal storage account and the tracking API plan
    for ep in S.network_endpoints():
        r = by_name[ep["origin"]]
        monthly = book.tiered_cost("bandwidth.internet_egress_gb", ep["egress_gb"])
        for d in range(1, S.DAYS + 1):
            rows.append(
                _row(
                    r,
                    d,
                    monthly / S.DAYS,
                    ep["egress_gb"] / S.DAYS,
                    "GB",
                    "bandwidth.internet_egress_gb",
                    "Internet data transfer out",
                    book.price("bandwidth.internet_egress_gb"),
                )
            )
    lake = by_name["stlkdatalake"]
    for x in S.cross_region_transfers():
        price = book.price("bandwidth.inter_region_gb")
        for d in range(1, S.DAYS + 1):
            rows.append(
                _row(
                    lake,
                    d,
                    x["gb_per_month"] * price / S.DAYS,
                    x["gb_per_month"] / S.DAYS,
                    "GB",
                    "bandwidth.inter_region_gb",
                    "Inter-region data transfer",
                    price,
                )
            )
    # batch pools run on pay-as-you-go today
    batch = by_name["batch-lk-prod"]
    for j in S.batch_jobs():
        price = book.price(vm_key(j["size"]))
        for d in _batch_days(j["runs_per_month"]):
            hrs = j["nodes"] * j["hours_per_run"]
            rows.append(
                _row(
                    batch,
                    d,
                    hrs * price,
                    hrs,
                    "Hours",
                    f"pool:{j['name']}:{j['size']}",
                    f"Batch pool {j['name']}",
                    price,
                )
            )
    # Azure OpenAI tokens, all on gpt-4o today
    aoai = by_name["aoai-lk-prod"]
    per_day: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    for q in S.ai_requests():
        per_day[q["day"]][0] += q["prompt_tokens"] * q["weight"]
        per_day[q["day"]][1] += q["completion_tokens"] * q["weight"]
    pin, pout = book.price("aoai.gpt-4o.input_1k"), book.price("aoai.gpt-4o.output_1k")
    for d in sorted(per_day):
        i, o = per_day[d]
        rows.append(
            _row(
                aoai,
                d,
                i / 1000 * pin,
                i / 1000,
                "1K tokens",
                "aoai.gpt-4o.input_1k",
                "gpt-4o input tokens",
                pin,
            )
        )
        rows.append(
            _row(
                aoai,
                d,
                o / 1000 * pout,
                o / 1000,
                "1K tokens",
                "aoai.gpt-4o.output_1k",
                "gpt-4o output tokens",
                pout,
            )
        )
    rows.sort(key=lambda x: (x["ChargePeriodStart"], x["ResourceId"], x["SkuId"]))
    return rows


def to_csv(rows: list[dict[str, Any]]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


@dataclass(frozen=True)
class CostRow:
    resource_id: str
    resource_name: str
    resource_type: str
    sub_account: str
    service: str
    sku: str
    day: str
    cost: float
    quantity: float
    tags: dict[str, str]


def read(text: str) -> list[CostRow]:
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        missing = [c for c in COLUMNS if c not in r]
        if missing:
            raise ValueError(f"not a FOCUS export this tool understands; missing {missing}")
        out.append(
            CostRow(
                r["ResourceId"],
                r["ResourceName"],
                r["ResourceType"],
                r["SubAccountId"],
                r["ServiceName"],
                r["SkuId"],
                r["ChargePeriodStart"][:10],
                float(r["EffectiveCost"]),
                float(r["ConsumedQuantity"]),
                json.loads(r["Tags"] or "{}"),
            )
        )
    return out


def cost_by_resource(rows: list[CostRow]) -> dict[str, float]:
    out: dict[str, float] = defaultdict(float)
    for r in rows:
        out[r.resource_id] += r.cost
    return dict(out)
