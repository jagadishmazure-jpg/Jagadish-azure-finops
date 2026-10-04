"""Pattern 10: cache and egress optimization (Front Door / CDN, Redis, data transfer).

Three levers, each priced from the list-price snapshot:
  * Edge caching with Front Door Standard for static content: compare internet egress from the
    origin with Front Door egress + request fees + base fee. ASSUMPTION: transfer from an Azure
    origin to Front Door is not charged (check current Front Door pricing for your origin type).
  * A Redis cache in front of a read-heavy API: the origin plan shrinks with the hit ratio
    (minimum 2 instances), minus the cache's own cost.
  * Cross-region copies: replicate only what changed instead of a full nightly copy.

Hit ratios and changed fractions are ASSUMPTIONS taken from the endpoint register; measure them
(Front Door cache-hit metric, Redis INFO stats, copy logs) before committing.
"""

from __future__ import annotations

import math

from finops.datasets import load_inventory, load_json
from finops.patterns.base import Finding, PatternResult
from finops.pricing import default_book

PATTERN = "p10-cache-egress"
REDIS_SKU = "redis.standard.C1"  # Standard has a replica; Basic has no SLA


def front_door_monthly(egress_gb: float, requests_10k: float) -> float:
    book = default_book()
    return (
        book.price("frontdoor.standard.base_month")
        + book.tiered_cost("frontdoor.standard.egress_gb", egress_gb)
        + book.tiered_cost("frontdoor.standard.requests_10k", requests_10k)
    )


def analyze() -> PatternResult:
    book = default_book()
    reg = load_json("network/endpoints.json")
    inv = {r["name"]: r for r in load_inventory()}
    res = PatternResult(PATTERN, "Cache and egress optimization", [])
    for ep in reg["endpoints"]:
        origin_egress = book.tiered_cost("bandwidth.internet_egress_gb", ep["egress_gb"])
        if ep.get("cache") == "redis":
            plan = inv[ep["origin_plan"]]
            n = plan["properties"]["instances"]
            unit = book.monthly(f"appservice.{plan['sku']}")
            new_n = max(2, math.ceil(n * (1 - ep["expected_hit_ratio"])))
            before = unit * n
            after = unit * new_n + book.monthly(REDIS_SKU)
            res.findings.append(
                Finding(
                    PATTERN,
                    plan["id"],
                    ep["name"],
                    f"Redis C1 cache-aside: {n} -> {new_n} {plan['sku']} instances",
                    before,
                    after,
                    confidence="medium",
                    risk="low",
                    change={"op": "add-cache", "sku": "Standard C1", "origin_instances": new_n},
                    evidence={
                        "hit_ratio": ep["expected_hit_ratio"],
                        "redis_monthly": round(book.monthly(REDIS_SKU), 2),
                    },
                    estimate=True,
                )
            )
            continue
        fd = front_door_monthly(ep["egress_gb"], ep["requests_10k"])
        if fd >= origin_egress:
            res.skipped.append(
                (
                    ep["name"],
                    f"Front Door ${fd:,.2f}/mo would not beat origin egress ${origin_egress:,.2f}/mo",
                )
            )
            continue
        res.findings.append(
            Finding(
                PATTERN,
                inv[ep["origin"]]["id"],
                ep["name"],
                "serve through Front Door Standard (edge cache)",
                origin_egress,
                fd,
                confidence="medium",
                risk="low",
                change={
                    "op": "front-door",
                    "sku": "Standard_AzureFrontDoor",
                    "caching": True,
                    "compression": True,
                },
                evidence={
                    "egress_gb": ep["egress_gb"],
                    "requests_10k": ep["requests_10k"],
                    "hit_ratio": ep["expected_hit_ratio"],
                    "origin_offload_gb": round(ep["egress_gb"] * ep["expected_hit_ratio"]),
                },
                estimate=True,
            )
        )
    price = book.price("bandwidth.inter_region_gb")
    for x in reg["cross_region"]:
        before = x["gb_per_month"] * price
        after = x["gb_per_month"] * x["changed_fraction"] * price
        res.findings.append(
            Finding(
                PATTERN,
                f"transfer:{x['name']}",
                x["name"],
                f"incremental copy ({x['changed_fraction']:.0%} changed) instead of full",
                before,
                after,
                confidence="high",
                risk="low",
                change={"op": "replication-mode", "to": "incremental"},
                evidence={
                    "gb_full": x["gb_per_month"],
                    "gb_incremental": round(x["gb_per_month"] * x["changed_fraction"]),
                },
                estimate=True,
            )
        )
    res.notes.append(
        "Front Door saving is mostly origin offload and latency; on egress alone the edge price is close to origin egress"
    )
    return res
