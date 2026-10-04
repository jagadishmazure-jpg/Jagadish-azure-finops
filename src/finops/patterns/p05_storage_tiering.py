"""Pattern 5: move cold blob data to cheaper tiers with a lifecycle policy.

For every container, data is bucketed by days since last access. Each bucket is priced in every
tier as storage + retrieval + read operations (``AVG_READ_MB`` per read) and the cheapest tier
that respects the constraints wins:

  * the bucket must be at least as old as the tier's minimum retention (cool 30, cold 90,
    archive 180 days), so no early-deletion charge applies;
  * archive needs offline rehydration (up to 15 hours at standard priority), so it is ruled out
    when the container's recovery objective is shorter;
  * containers under legal hold are left alone until compliance signs off.

The output is a ready-to-apply ``Microsoft.Storage`` management (lifecycle) policy.
"""

from __future__ import annotations

from typing import Any

from finops.datasets import load_json
from finops.patterns.base import Finding, PatternResult
from finops.pricing import default_book

PATTERN = "p05-storage-tiering"
TIERS = ["hot", "cool", "cold", "archive"]
MIN_DAYS = {"hot": 0, "cool": 30, "cold": 90, "archive": 180}
ARCHIVE_REHYDRATE_HOURS = 15
AVG_READ_MB = 4.0  # ASSUMPTION used to turn GB read into read operations


def bucket_cost(tier: str, gb: float, read_gb: float) -> float:
    book = default_book()
    store = book.price(f"blob.{tier}.gb_month") * gb
    retrieval = 0.0 if tier == "hot" else book.price(f"blob.{tier}.retrieval_gb") * read_gb
    ops = read_gb * 1024 / AVG_READ_MB / 10_000 * book.price(f"blob.{tier}.read_10k")
    return store + retrieval + ops


def choose_tier(bucket: dict[str, Any], rehydrate_hours: float) -> tuple[str, dict[str, float]]:
    costs = {}
    for t in TIERS:
        if bucket["min_age"] < MIN_DAYS[t]:
            continue
        if t == "archive" and rehydrate_hours < ARCHIVE_REHYDRATE_HOURS:
            continue
        costs[t] = round(bucket_cost(t, bucket["gb"], bucket["read_gb"]), 2)
    return min(costs, key=lambda k: (costs[k], TIERS.index(k))), costs


def lifecycle_policy(plan: dict[str, dict[int, str]]) -> dict[str, Any]:
    """Build a management policy: one rule per container, tiering on days since last access."""
    rules = []
    for container, by_age in sorted(plan.items()):
        actions: dict[str, Any] = {}
        for age, tier in sorted(by_age.items()):
            if tier == "hot":
                continue
            key = {"cool": "tierToCool", "cold": "tierToCold", "archive": "tierToArchive"}[tier]
            actions.setdefault(key, {"daysAfterLastAccessTimeGreaterThan": age})  # earliest age per tier
        if not actions:
            continue
        if "tierToCool" in actions:
            actions["enableAutoTierToHotFromCool"] = True
        rules.append(
            {
                "name": f"tier-{container}",
                "enabled": True,
                "type": "Lifecycle",
                "definition": {
                    "filters": {"blobTypes": ["blockBlob"], "prefixMatch": [f"{container}/"]},
                    "actions": {"baseBlob": actions},
                },
            }
        )
    return {"policy": {"rules": rules}}


def analyze() -> PatternResult:
    book = default_book()
    res = PatternResult(PATTERN, "Storage lifecycle tiering (hot -> cool -> cold -> archive)", [])
    plan: dict[str, dict[int, str]] = {}
    for c in load_json("storage/containers.json"):
        if c["legal_hold"]:
            res.skipped.append((c["container"], "legal hold; tier changes need compliance sign-off"))
            continue
        before = after = 0.0
        moves = {}
        priced = []
        for b in c["buckets"]:
            tier, costs = choose_tier(b, c["max_rehydrate_hours"])
            priced.append(
                {
                    "min_age": b["min_age"],
                    "gb": b["gb"],
                    "read_gb": b["read_gb"],
                    "tier": tier,
                    "monthly_by_tier": costs,
                }
            )
            before += bucket_cost("hot", b["gb"], b["read_gb"])
            after += costs[tier]
            moves[b["min_age"]] = tier
        if all(t == "hot" for t in moves.values()):
            res.skipped.append((c["container"], "every bucket is cheapest in hot (read-heavy)"))
            continue
        plan[c["container"]] = moves
        path = " / ".join(f"{a}d+:{t}" for a, t in sorted(moves.items()))
        res.findings.append(
            Finding(
                PATTERN,
                f"{c['account']}/{c['container']}",
                f"{c['account']}/{c['container']}",
                f"lifecycle {path}",
                before,
                after,
                confidence="high",
                risk="low" if "archive" not in moves.values() else "medium",
                change={"op": "lifecycle-policy", "container": c["container"]},
                evidence={"buckets": priced, "rehydrate_objective_hours": c["max_rehydrate_hours"]},
                estimate=True,
            )
        )
    res.extra["policy"] = lifecycle_policy(plan)
    res.notes.append(
        f"ASSUMPTION {AVG_READ_MB:.0f} MB per read operation; prices are the flat first tier ({book.price('blob.hot.gb_month')}/GB hot)"
    )
    res.notes.append(
        "requires last-access-time tracking on the account; first transition writes are a one-off cost not shown"
    )
    return res
