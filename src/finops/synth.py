"""Deterministic synthetic estate for Larkspur Freight (a fictional logistics company).

Everything the scenarios read is generated here from fixed seeds and written to ``data/`` by
``scripts/generate_data.py``. A test regenerates it in memory and compares, so the checked-in
files can never drift from the generator. There is no real customer data, no subscription GUID
and no tenant ID anywhere: subscriptions are short aliases such as ``lk-prod``.
"""

from __future__ import annotations

import math
import random
from typing import Any

AKS_NODE_CORES = 3.6  # allocatable cores per D4s_v5 node
AKS_TARGET = 0.8  # target node CPU utilization
HOURS = 720  # a 30-day observation window, hourly
DAYS = 30

COST_CENTERS = {
    "CC-1001": "Dispatch & Integration",
    "CC-2002": "Customer Portal",
    "CC-3003": "Data & Analytics",
    "CC-4004": "Platform",
    "CC-5005": "AI Assistants",
}


def rid(sub: str, rg: str, rtype: str, name: str) -> str:
    return f"/subscriptions/{sub}/resourceGroups/{rg}/providers/{rtype}/{name}"


def _tags(cc: str | None, env: str, owner: str, app: str) -> dict[str, str]:
    t = {"env": env, "owner": owner, "app": app}
    if cc:
        t["cost-center"] = cc
    return t


VM = "Microsoft.Compute/virtualMachines"
DISK = "Microsoft.Compute/disks"
PIP = "Microsoft.Network/publicIPAddresses"
NIC = "Microsoft.Network/networkInterfaces"
PLAN = "Microsoft.Web/serverfarms"
SITE = "Microsoft.Web/sites"
CAPP = "Microsoft.App/containerApps"
AKS = "Microsoft.ContainerService/managedClusters"
STG = "Microsoft.Storage/storageAccounts"
LAW = "Microsoft.OperationalInsights/workspaces"
BATCH = "Microsoft.Batch/batchAccounts"
AOAI = "Microsoft.CognitiveServices/accounts"


def _r(sub, rg, rtype, name, sku, tags, **props) -> dict[str, Any]:
    return {
        "id": rid(sub, rg, rtype, name),
        "name": name,
        "type": rtype,
        "subscription": sub,
        "resourceGroup": rg,
        "location": "eastus2",
        "sku": sku,
        "tags": tags,
        "properties": props,
    }


def inventory() -> list[dict[str, Any]]:
    P, N = "lk-prod", "lk-nonprod"
    res = [
        # --- Dispatch (CC-1001)
        _r(
            P,
            "rg-dispatch-prod",
            VM,
            "vm-dispatch-api-01",
            "D8s_v5",
            _tags("CC-1001", "prod", "dispatch-team", "dispatch-api"),
            os="linux",
            power_state="running",
            profile="low",
        ),
        _r(
            P,
            "rg-dispatch-prod",
            VM,
            "vm-dispatch-api-02",
            "D8s_v5",
            _tags("CC-1001", "prod", "dispatch-team", "dispatch-api"),
            os="linux",
            power_state="running",
            profile="low",
        ),
        _r(
            P,
            "rg-dispatch-prod",
            VM,
            "vm-dispatch-db-01",
            "E4s_v5",
            _tags("CC-1001", "prod", "dispatch-team", "dispatch-db"),
            os="windows",
            power_state="running",
            profile="memory-bound",
            sql_edition="standard",
            license_type=None,
        ),
        _r(
            P,
            "rg-dispatch-prod",
            VM,
            "vm-dispatch-legacy-01",
            "D4s_v5",
            _tags("CC-1001", "prod", "dispatch-team", "legacy-scheduler"),
            os="windows",
            power_state="running",
            profile="idle-ish",
            license_type=None,
        ),
        _r(
            P,
            "rg-dispatch-prod",
            AKS,
            "aks-dispatch-prod",
            "D4s_v5",
            _tags("CC-1001", "prod", "dispatch-team", "dispatch-workers"),
            node_count=6,
            autoscaler=False,
            profile="aks-diurnal",
        ),
        _r(
            P,
            "rg-integration-prod",
            SITE,
            "la-invoice-intake",
            "WS1",
            _tags("CC-1001", "prod", "integration-team", "invoice-intake"),
            kind="workflowapp",
            plan_vcpu=1,
            plan_gib=3.5,
            monthly_runs=2000,
            actions_per_run=12,
            workflows=3,
            needs_vnet=False,
        ),
        _r(
            P,
            "rg-integration-prod",
            SITE,
            "fn-label-print",
            "EP1",
            _tags("CC-1001", "prod", "integration-team", "label-print"),
            kind="functionapp",
            plan_vcpu=1,
            plan_gib=3.5,
            monthly_executions=120000,
            avg_duration_s=0.4,
            memory_gb=0.5,
            needs_vnet=False,
            max_cold_start_s=10,
        ),
        _r(
            P,
            "rg-integration-prod",
            SITE,
            "fn-telemetry-ingest",
            "EP1",
            _tags("CC-1001", "prod", "integration-team", "telemetry-ingest"),
            kind="functionapp",
            plan_vcpu=1,
            plan_gib=3.5,
            monthly_executions=900_000_000,
            avg_duration_s=0.25,
            memory_gb=0.5,
            needs_vnet=False,
            max_cold_start_s=10,
        ),
        # --- Customer portal (CC-2002)
        _r(
            P,
            "rg-portal-prod",
            PLAN,
            "asp-portal-prod",
            "P1v3",
            _tags("CC-2002", "prod", "web-team", "customer-portal"),
            instances=6,
            apps=2,
            autoscale=False,
            profile="web-weekly",
            rps_per_instance=250,
        ),
        _r(
            P,
            "rg-portal-prod",
            PLAN,
            "asp-partner-api",
            "P2v3",
            _tags("CC-2002", "prod", "web-team", "partner-api"),
            instances=2,
            apps=1,
            autoscale=False,
            profile="low",
        ),
        _r(
            P,
            "rg-portal-prod",
            PLAN,
            "asp-tracking-prod",
            "P1v3",
            _tags("CC-2002", "prod", "web-team", "tracking-api"),
            instances=4,
            apps=1,
            autoscale=False,
            profile="steady",
        ),
        _r(
            P,
            "rg-portal-prod",
            STG,
            "stlkportalassets",
            "Standard_LRS",
            _tags("CC-2002", "prod", "web-team", "customer-portal"),
            containers=[],
        ),
        # --- Data (CC-3003)
        _r(
            P,
            "rg-data-prod",
            VM,
            "vm-etl-01",
            "E4s_v5",
            _tags("CC-3003", "prod", "data-team", "etl"),
            os="linux",
            power_state="running",
            profile="memory-bound",
        ),
        _r(
            P,
            "rg-data-prod",
            VM,
            "vm-report-01",
            "D4s_v5",
            _tags("CC-3003", "prod", "data-team", "reporting"),
            os="linux",
            power_state="running",
            profile="idle-ish",
        ),
        _r(
            P,
            "rg-data-prod",
            STG,
            "stlkdatalake",
            "Standard_LRS",
            _tags("CC-3003", "prod", "data-team", "data-lake"),
            containers=["raw-telemetry", "shipment-docs", "audit-archive", "ml-features"],
        ),
        _r(
            P,
            "rg-data-prod",
            BATCH,
            "batch-lk-prod",
            "D8s_v5",
            _tags("CC-3003", "prod", "data-team", "batch"),
            pools=["route-optimizer", "invoice-render", "month-end-close", "eta-model-train"],
        ),
        # --- Platform (CC-4004)
        _r(
            P,
            "rg-platform-prod",
            VM,
            "vm-build-01",
            "D4s_v5",
            _tags("CC-4004", "prod", "platform-team", "build-agent"),
            os="linux",
            power_state="running",
            profile="busy",
        ),
        _r(
            P,
            "rg-platform-prod",
            VM,
            "vm-jump-01",
            "D2s_v5",
            _tags("CC-4004", "prod", "platform-team", "jumpbox"),
            os="windows",
            power_state="running",
            profile="moderate",
            license_type=None,
        ),
        _r(
            P,
            "rg-platform-prod",
            LAW,
            "log-lk-prod",
            "PerGB2018",
            _tags("CC-4004", "prod", "platform-team", "observability"),
            ingest_gb_per_day=12.0,
            shared=True,
        ),
        # --- AI (CC-5005)
        _r(
            P,
            "rg-ai-prod",
            AOAI,
            "aoai-lk-prod",
            "S0",
            _tags("CC-5005", "prod", "ai-team", "assistants"),
            deployments=["gpt-4o", "gpt-4o-mini"],
        ),
        _r(
            P,
            "rg-ai-prod",
            CAPP,
            "ca-eta-assistant",
            "consumption",
            _tags("CC-5005", "prod", "ai-team", "eta-assistant"),
            min_replicas=1,
            vcpu=0.5,
            gib=1.0,
            active_fraction=0.62,
            monthly_requests=410000,
        ),
        # --- Non-prod: dev apps that idle overnight
        _r(
            N,
            "rg-dispatch-dev",
            CAPP,
            "ca-dispatch-dev-api",
            "consumption",
            _tags("CC-1001", "dev", "dispatch-team", "dispatch-api"),
            min_replicas=2,
            vcpu=1.0,
            gib=2.0,
            active_fraction=0.18,
            monthly_requests=52000,
        ),
        _r(
            N,
            "rg-dispatch-dev",
            CAPP,
            "ca-dispatch-dev-worker",
            "consumption",
            _tags("CC-1001", "dev", "dispatch-team", "dispatch-worker"),
            min_replicas=1,
            vcpu=1.0,
            gib=2.0,
            active_fraction=0.10,
            monthly_requests=0,
            queue_driven=True,
        ),
        # --- Non-prod: leftovers (idle cleanup)
        _r(
            N,
            "rg-sandbox-migration",
            DISK,
            "disk-migr-data-01",
            "P30",
            _tags(None, "sandbox", "unknown", "migration-test"),
            disk_state="Unattached",
            days_unattached=64,
            size_gb=1024,
        ),
        _r(
            N,
            "rg-sandbox-migration",
            DISK,
            "disk-migr-data-02",
            "P10",
            _tags(None, "sandbox", "unknown", "migration-test"),
            disk_state="Unattached",
            days_unattached=64,
            size_gb=128,
        ),
        _r(
            N,
            "rg-dispatch-dev",
            DISK,
            "disk-dev-scratch-01",
            "E10",
            _tags("CC-1001", "dev", "dispatch-team", "scratch"),
            disk_state="Unattached",
            days_unattached=2,
            size_gb=128,
        ),
        _r(
            N,
            "rg-sandbox-migration",
            PIP,
            "pip-migr-gw-01",
            "Standard",
            _tags(None, "sandbox", "unknown", "migration-test"),
            associated=False,
            days_unassociated=41,
        ),
        _r(
            N,
            "rg-sandbox-migration",
            PIP,
            "pip-migr-gw-02",
            "Standard",
            _tags(None, "sandbox", "unknown", "migration-test") | {"finops-exempt": "true"},
            associated=False,
            days_unassociated=41,
        ),
        _r(
            N,
            "rg-dispatch-dev",
            PIP,
            "pip-dev-lb-01",
            "Standard",
            _tags("CC-1001", "dev", "dispatch-team", "dispatch-api"),
            associated=False,
            days_unassociated=1,
        ),
        _r(
            N,
            "rg-sandbox-migration",
            NIC,
            "nic-migr-vm-01",
            "n/a",
            _tags(None, "sandbox", "unknown", "migration-test"),
            attached=False,
        ),
        _r(
            N,
            "rg-sandbox-poc",
            PLAN,
            "asp-poc-empty",
            "P1v3",
            _tags("CC-2002", "sandbox", "web-team", "poc"),
            instances=1,
            apps=0,
            autoscale=False,
            profile="flat-zero",
        ),
        _r(
            N,
            "rg-sandbox-poc",
            VM,
            "vm-poc-gpu-replacement",
            "D4s_v5",
            _tags("CC-3003", "sandbox", "data-team", "poc"),
            os="linux",
            power_state="stopped",
            profile="flat-zero",
        ),
        _r(
            N,
            "rg-sandbox-poc",
            VM,
            "vm-poc-old-ui",
            "D2s_v5",
            _tags(None, "sandbox", "unknown", "poc"),
            os="linux",
            power_state="deallocated",
            profile="flat-zero",
        ),
    ]
    return res


# ------------------------------------------------------------------ utilization series
def _series(
    rng: random.Random, base: float, amp: float, noise: float, spike_every: int = 0, spike: float = 0.0
) -> list[float]:
    out = []
    for h in range(HOURS):
        hour = h % 24
        weekday = (h // 24) % 7 < 5
        diurnal = max(0.0, math.sin(math.pi * (hour - 7) / 12)) if 7 <= hour <= 19 else 0.0
        v = base + amp * diurnal * (1.0 if weekday else 0.4) + rng.gauss(0, noise)
        if spike_every and h % spike_every == spike_every - 1:
            v += spike
        out.append(round(min(100.0, max(0.0, v)), 1))
    return out


PROFILES = {
    # name: (cpu base, cpu amp, cpu noise, mem base, mem amp, mem noise)
    "low": (8, 12, 2.0, 24, 8, 1.5),
    "idle-ish": (4, 5, 1.0, 18, 3, 1.0),
    "memory-bound": (20, 25, 4.0, 70, 8, 2.0),
    "busy": (45, 30, 6.0, 55, 10, 3.0),
    "moderate": (15, 20, 4.0, 40, 10, 2.0),
    "steady": (30, 20, 4.0, 45, 5, 2.0),
    "flat-zero": (0.5, 0, 0.2, 5, 0, 0.5),
}


def utilization(inv: list[dict[str, Any]]) -> dict[str, dict[str, list[float]]]:
    out: dict[str, dict[str, list[float]]] = {}
    for i, r in enumerate(inv):
        prof = r["properties"].get("profile")
        if prof not in PROFILES:
            continue
        rng = random.Random(1000 + i)
        cb, ca, cn, mb, ma, mn = PROFILES[prof]
        spike_every = 168 if r["name"] == "vm-dispatch-api-02" else 0  # weekly batch spike
        out[r["id"]] = {
            "cpu": _series(rng, cb, ca, cn, spike_every, 70.0),
            "mem": _series(rng, mb, ma, mn),
        }
    return out


def web_traffic() -> dict[str, list[float]]:
    """One week (168 hourly points) of requests per second for the elastic apps."""
    rng = random.Random(7)
    portal = []
    aks = []
    for h in range(168):
        hour, day = h % 24, h // 24
        weekday = day < 5
        shape = max(0.0, math.sin(math.pi * (hour - 6) / 14)) if 6 <= hour <= 20 else 0.0
        portal.append(round(60 + 840 * shape * (1.0 if weekday else 0.35) + rng.gauss(0, 15), 1))
        # AKS: pod CPU cores demanded across the cluster
        aks.append(round(max(2.0, 4 + 12 * shape * (1.0 if weekday else 0.5) + rng.gauss(0, 0.6)), 2))
    return {"asp-portal-prod.rps": portal, "aks-dispatch-prod.pod_cores": aks}


def compute_usage(inv: list[dict[str, Any]]) -> list[float]:
    """Hourly D-series usage in normalized D2s_v5 units (instance size flexibility) AFTER rightsizing.

    Steady base: 2x D4s_v5 dispatch api (post-rightsize) + build agent + report D2 = 9 units, plus
    the AKS pool following demand and a business-hours burst of short-lived build and test VMs.
    Spot batch pools are excluded: they are never covered by a commitment.
    """
    traffic = web_traffic()["aks-dispatch-prod.pod_cores"]
    rng = random.Random(11)
    out = []
    for h in range(HOURS):
        hour, weekday = h % 24, (h // 24) % 7 < 5
        aks_nodes = max(2, math.ceil(traffic[h % 168] / (AKS_NODE_CORES * AKS_TARGET)))
        burst = 6 if weekday and 9 <= hour < 17 else 0
        units = 9 + aks_nodes * 2 + burst + (rng.random() < 0.02) * 2
        out.append(float(units))
    return out


def batch_jobs() -> list[dict[str, Any]]:
    return [
        {
            "name": "route-optimizer",
            "size": "D8s_v5",
            "nodes": 10,
            "hours_per_run": 3.0,
            "runs_per_month": 30,
            "interruptible": True,
            "checkpoint_minutes": 15,
            "deadline_hours": 6.0,
        },
        {
            "name": "invoice-render",
            "size": "D4s_v5",
            "nodes": 4,
            "hours_per_run": 2.0,
            "runs_per_month": 30,
            "interruptible": True,
            "checkpoint_minutes": 10,
            "deadline_hours": 4.0,
        },
        {
            "name": "eta-model-train",
            "size": "E4s_v5",
            "nodes": 6,
            "hours_per_run": 5.0,
            "runs_per_month": 8,
            "interruptible": True,
            "checkpoint_minutes": 30,
            "deadline_hours": 12.0,
        },
        {
            "name": "month-end-close",
            "size": "D8s_v5",
            "nodes": 2,
            "hours_per_run": 6.0,
            "runs_per_month": 1,
            "interruptible": False,
            "checkpoint_minutes": 0,
            "deadline_hours": 7.0,
        },
    ]


def storage_containers() -> list[dict[str, Any]]:
    """GB stored and GB read per month, bucketed by days since last access."""
    return [
        {
            "account": "stlkdatalake",
            "container": "raw-telemetry",
            "legal_hold": False,
            "max_rehydrate_hours": 48,
            "buckets": [
                {"min_age": 0, "gb": 4200, "read_gb": 9000},
                {"min_age": 30, "gb": 11800, "read_gb": 600},
                {"min_age": 90, "gb": 26500, "read_gb": 40},
                {"min_age": 180, "gb": 61000, "read_gb": 5},
            ],
        },
        {
            "account": "stlkdatalake",
            "container": "shipment-docs",
            "legal_hold": False,
            "max_rehydrate_hours": 1,
            "buckets": [
                {"min_age": 0, "gb": 900, "read_gb": 2600},
                {"min_age": 30, "gb": 3100, "read_gb": 310},
                {"min_age": 90, "gb": 7400, "read_gb": 120},
                {"min_age": 180, "gb": 15800, "read_gb": 60},
            ],
        },
        {
            "account": "stlkdatalake",
            "container": "audit-archive",
            "legal_hold": True,
            "max_rehydrate_hours": 48,
            "buckets": [{"min_age": 0, "gb": 150, "read_gb": 2}, {"min_age": 180, "gb": 9800, "read_gb": 0}],
        },
        {
            "account": "stlkdatalake",
            "container": "ml-features",
            "legal_hold": False,
            "max_rehydrate_hours": 1,
            "buckets": [
                {"min_age": 0, "gb": 2400, "read_gb": 48000},
                {"min_age": 30, "gb": 600, "read_gb": 900},
            ],
        },
    ]


def license_entitlements() -> dict[str, Any]:
    return {
        "windows_server_datacenter_cores_with_sa": 16,
        "sql_standard_cores_with_sa": 4,
        "sql_enterprise_cores_with_sa": 0,
        "notes": "Synthetic entitlement register. Real assessments read the license agreement and Software Assurance records.",
    }


def network_endpoints() -> list[dict[str, Any]]:
    return [
        {
            "name": "portal-static",
            "origin": "stlkportalassets",
            "egress_gb": 18000,
            "requests_10k": 9000,
            "cacheable": 0.9,
            "expected_hit_ratio": 0.85,
            "origin_plan": None,
        },
        {
            "name": "tracking-api",
            "origin": "asp-tracking-prod",
            "egress_gb": 2200,
            "requests_10k": 31000,
            "cacheable": 0.7,
            "expected_hit_ratio": 0.7,
            "origin_plan": "asp-tracking-prod",
            "cache": "redis",
        },
    ]


def cross_region_transfers() -> list[dict[str, Any]]:
    return [
        {
            "name": "nightly-lake-copy",
            "from": "eastus2",
            "to": "westus2",
            "gb_per_month": 42000,
            "changed_fraction": 0.12,
            "purpose": "DR copy of the data lake (full copy each night)",
        }
    ]


def allocation_rules() -> dict[str, Any]:
    return {
        "cost_centers": COST_CENTERS,
        "resource_group_owner": {
            "rg-sandbox-migration": "CC-4004",
            "rg-sandbox-poc": "CC-3003",
        },
        "shared": {"rg-platform-prod/log-lk-prod": "proportional"},
        "budgets": {"CC-1001": 3400, "CC-2002": 3800, "CC-3003": 4500, "CC-4004": 600, "CC-5005": 700},
        "alert_thresholds": [0.5, 0.8, 1.0],
        "required_tags": ["cost-center", "owner", "env", "app"],
    }


# ------------------------------------------------------------------ AI requests
TENANTS = ["tenant-acme-retail", "tenant-bluebird-pharma", "tenant-cobalt-auto", "internal"]
AGENTS = {
    "eta-assistant": "customer-eta-chat",
    "invoice-triage": "invoice-exception-triage",
    "dispatch-summarizer": "dispatch-shift-summary",
}
SIMPLE_Q = [
    "where is shipment {n}",
    "what is the eta for order {n}",
    "track parcel {n}",
    "is delivery {n} late",
    "show status of load {n}",
    "can you tell me whether the delivery for order {n} still arrives today",  # long but simple
]
TRICKY_COMPLEX = "eta impact of the port strike on lane {n}"  # short, sounds simple, needs reasoning
COMPLEX_Q = [
    "invoice {n} has a rate mismatch against contract terms and a fuel surcharge dispute, explain and propose a resolution",
    "summarize the dispatch shift including exceptions, driver hours risks and reroutes for depot {n}",
    "customer claims damaged freight on load {n}, review the proof of delivery notes and draft a reply",
    "compare carrier performance for lane {n} over the quarter and recommend changes",
]


AI_SAMPLE_WEIGHT = 10  # the request log is a 1-in-10 sample of a month of traffic


def ai_requests(count: int = 6000) -> list[dict[str, Any]]:
    rng = random.Random(42)
    out = []
    for i in range(count):
        agent = rng.choices(list(AGENTS), weights=[0.62, 0.23, 0.15])[0]
        tenant = rng.choices(TENANTS, weights=[0.4, 0.25, 0.2, 0.15])[0]
        complex_ = agent != "eta-assistant" or rng.random() < 0.08
        if complex_:
            tmpl = (
                TRICKY_COMPLEX if agent == "eta-assistant" and rng.random() < 0.3 else rng.choice(COMPLEX_Q)
            )
            n = rng.randint(100, 999)
            prompt_tokens = rng.randint(2600, 5000)
            completion_tokens = rng.randint(350, 900)
        else:
            tmpl = rng.choice(SIMPLE_Q)
            n = rng.randint(1000, 1060)  # small id space -> repeated questions -> cache hits
            prompt_tokens = rng.randint(1400, 1800)
            completion_tokens = rng.randint(60, 160)
        out.append(
            {
                "request_id": f"r{i:05d}",
                "day": i * DAYS // count + 1,
                "tenant": tenant,
                "agent": agent,
                "use_case": AGENTS[agent],
                "prompt": tmpl.format(n=n),
                "system_prefix_tokens": 1280,  # system prompt + tool schemas, identical on every call
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "label": "complex" if complex_ else "simple",
                "model": "gpt-4o",
                "weight": AI_SAMPLE_WEIGHT,
            }
        )
    return out


def ai_use_cases() -> list[dict[str, Any]]:
    """Business inputs for ROI. Value drivers are ASSUMPTIONS a coach agrees with the business owner."""
    return [
        {
            "use_case": "customer-eta-chat",
            "owner": "CC-2002",
            "minutes_saved_per_task": 1.5,
            "loaded_rate_per_hour": 38.0,
            "adoption": 0.6,
            "build_cost": 42000,
            "amortize_months": 24,
            "platform_monthly": 180.0,
        },
        {
            "use_case": "invoice-exception-triage",
            "owner": "CC-1001",
            "minutes_saved_per_task": 6.0,
            "loaded_rate_per_hour": 52.0,
            "adoption": 0.5,
            "build_cost": 65000,
            "amortize_months": 24,
            "platform_monthly": 220.0,
        },
        {
            "use_case": "dispatch-shift-summary",
            "owner": "CC-1001",
            "minutes_saved_per_task": 1.0,
            "loaded_rate_per_hour": 45.0,
            "adoption": 0.15,
            "build_cost": 30000,
            "amortize_months": 24,
            "platform_monthly": 160.0,
        },
    ]


def ai_budgets() -> dict[str, Any]:
    return {
        "tenant_monthly_usd": {
            "tenant-acme-retail": 170.0,
            "tenant-bluebird-pharma": 130.0,
            "tenant-cobalt-auto": 80.0,
            "internal": 75.0,
        },
        "agent_monthly_usd": {"eta-assistant": 150.0, "invoice-triage": 200.0, "dispatch-summarizer": 100.0},
        "soft_alert": 0.8,
        "degrade_at": 1.0,
        "block_at": 1.2,
        "critical_agents": ["invoice-triage"],
    }


# ------------------------------------------------------------------ case study (anonymized)
def case_study() -> dict[str, Any]:
    """Anonymized reproduction of a pattern seen in a real review: an idle Logic Apps Standard
    WS1 plan and a Container App held warm by minReplicas=1. Names and numbers are synthetic."""
    S = "cs-practice"
    return {
        "inventory": [
            _r(
                S,
                "rg-practice-integration",
                PLAN,
                "asp-practice-ws1",
                "WS1",
                _tags(None, "practice", "unknown", "logic-apps-trial"),
                kind="workflowapp-plan",
                plan_vcpu=1,
                plan_gib=3.5,
                apps=1,
                workflow_runs_30d=0,
                last_run_days_ago=47,
            ),
            _r(
                S,
                "rg-practice-integration",
                SITE,
                "la-practice-orders",
                "WS1",
                _tags(None, "practice", "unknown", "logic-apps-trial"),
                kind="workflowapp",
                plan="asp-practice-ws1",
                workflows=2,
                monthly_runs=0,
                actions_per_run=6,
            ),
            _r(
                S,
                "rg-practice-agent",
                CAPP,
                "ca-practice-agent",
                "consumption",
                _tags(None, "practice", "unknown", "agent-trial"),
                min_replicas=1,
                vcpu=0.5,
                gib=1.0,
                active_fraction=0.0,
                monthly_requests=0,
            ),
        ],
    }
