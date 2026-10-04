"""Generate (``generate_all``) and load (``load_*``) the checked-in synthetic datasets."""

from __future__ import annotations

import json
from functools import cache
from typing import Any

from finops import DATA
from finops import focus as F
from finops import synth as S


def _j(obj: Any) -> str:
    return json.dumps(obj, indent=1, sort_keys=True) + "\n"


def generate_all() -> dict[str, str]:
    inv = S.inventory()
    cs = S.case_study()
    return {
        "inventory/resources.json": _j(inv),
        "metrics/utilization.json": json.dumps(S.utilization(inv), sort_keys=True, separators=(",", ":")) + "\n",
        "metrics/web-traffic.json": _j(S.web_traffic()),
        "metrics/compute-usage.json": _j({"unit": "D2s_v5-equivalent instances (instance size flexibility)", "hourly": S.compute_usage(inv)}),
        "batch/jobs.json": _j(S.batch_jobs()),
        "storage/containers.json": _j(S.storage_containers()),
        "licenses/entitlements.json": _j(S.license_entitlements()),
        "network/endpoints.json": _j({"endpoints": S.network_endpoints(), "cross_region": S.cross_region_transfers()}),
        "allocation/rules.json": _j(S.allocation_rules()),
        "focus/cost-export.csv": F.to_csv(F.generate()),
        "ai/requests.jsonl": "".join(json.dumps(r, sort_keys=True) + "\n" for r in S.ai_requests()),
        "ai/use-cases.json": _j(S.ai_use_cases()),
        "ai/budgets.json": _j(S.ai_budgets()),
        "case-study/inventory.json": _j(cs["inventory"]),
    }


def _read(rel: str) -> str:
    return (DATA / rel).read_text()


@cache
def load_inventory() -> list[dict[str, Any]]:
    return json.loads(_read("inventory/resources.json"))


@cache
def load_utilization() -> dict[str, dict[str, list[float]]]:
    return json.loads(_read("metrics/utilization.json"))


@cache
def load_traffic() -> dict[str, list[float]]:
    return json.loads(_read("metrics/web-traffic.json"))


@cache
def load_compute_usage() -> list[float]:
    return json.loads(_read("metrics/compute-usage.json"))["hourly"]


@cache
def load_json(rel: str) -> Any:
    return json.loads(_read(rel))


@cache
def load_focus() -> list[F.CostRow]:
    return F.read(_read("focus/cost-export.csv"))


@cache
def load_ai_requests() -> list[dict[str, Any]]:
    return [json.loads(line) for line in _read("ai/requests.jsonl").splitlines() if line.strip()]


def by_name(name: str) -> dict[str, Any]:
    for r in load_inventory():
        if r["name"] == name:
            return r
    raise KeyError(name)
