"""Pattern 2: autoscale elastic apps instead of provisioning for peak.

Three surfaces, one idea (capacity follows demand):
  * App Service plan: instance count from requests per second, target 70 % of tested capacity
    per instance, minimum 2 for availability, maximum 10.
  * AKS: cluster autoscaler + HPA. Nodes needed = pod CPU demand / (allocatable cores x 80 %),
    minimum 2 nodes.
  * Container Apps: scale to zero (minReplicas=0) for non-prod HTTP apps and queue workers
    (KEDA scaler). Prod apps with a latency objective keep a warm replica.

Savings are computed by replaying one measured week of demand hour by hour.
"""

from __future__ import annotations

import math

import yaml

from finops import HOURS_PER_MONTH
from finops import synth as S
from finops.costing import container_app_monthly, monthly_cost
from finops.datasets import load_inventory, load_traffic
from finops.patterns.base import Finding, PatternResult
from finops.pricing import default_book, vm_key

PATTERN = "p02-autoscale"
APP_TARGET = 0.70
APP_MIN, APP_MAX = 2, 10
AKS_MIN = 2


def instances_needed(
    rps: float, per_instance: float, target: float = APP_TARGET, lo: int = APP_MIN, hi: int = APP_MAX
) -> int:
    return min(hi, max(lo, math.ceil(rps / (per_instance * target))))


def replay_app_service(rps_week: list[float], per_instance: float) -> tuple[float, int]:
    """Average instances over the week and the peak count."""
    counts = [instances_needed(x, per_instance) for x in rps_week]
    return sum(counts) / len(counts), max(counts)


def replay_aks(cores_week: list[float]) -> tuple[float, int]:
    nodes = [max(AKS_MIN, math.ceil(c / (S.AKS_NODE_CORES * S.AKS_TARGET))) for c in cores_week]
    return sum(nodes) / len(nodes), max(nodes)


def app_service_autoscale_profile(per_instance: float) -> dict:
    """Azure Monitor autoscale profile (same shape as the ARM/Bicep `profiles` element)."""

    def rule(direction: str, op: str, threshold: int, cooldown: str) -> dict:
        return {
            "metricTrigger": {
                "metricName": "CpuPercentage",
                "operator": op,
                "threshold": threshold,
                "timeAggregation": "Average",
                "statistic": "Average",
                "timeGrain": "PT1M",
                "timeWindow": "PT10M",
            },
            "scaleAction": {
                "direction": direction,
                "type": "ChangeCount",
                "value": "1",
                "cooldown": cooldown,
            },
        }

    return {
        "name": "follow-demand",
        "capacity": {"minimum": str(APP_MIN), "maximum": str(APP_MAX), "default": str(APP_MIN)},
        "rules": [rule("Increase", "GreaterThan", 70, "PT5M"), rule("Decrease", "LessThan", 35, "PT15M")],
        "x-tested-rps-per-instance": per_instance,
    }


def hpa_manifest(name: str) -> str:
    return yaml.safe_dump(
        {
            "apiVersion": "autoscaling/v2",
            "kind": "HorizontalPodAutoscaler",
            "metadata": {"name": name},
            "spec": {
                "scaleTargetRef": {"apiVersion": "apps/v1", "kind": "Deployment", "name": name},
                "minReplicas": 2,
                "maxReplicas": 30,
                "metrics": [
                    {
                        "type": "Resource",
                        "resource": {
                            "name": "cpu",
                            "target": {"type": "Utilization", "averageUtilization": 70},
                        },
                    }
                ],
                "behavior": {"scaleDown": {"stabilizationWindowSeconds": 300}},
            },
        },
        sort_keys=False,
    )


def keda_scaledobject(name: str, queue: str) -> str:
    return yaml.safe_dump(
        {
            "apiVersion": "keda.sh/v1alpha1",
            "kind": "ScaledObject",
            "metadata": {"name": name},
            "spec": {
                "scaleTargetRef": {"name": name},
                "minReplicaCount": 0,
                "maxReplicaCount": 10,
                "cooldownPeriod": 300,
                "triggers": [
                    {
                        "type": "azure-servicebus",
                        "metadata": {"queueName": queue, "messageCount": "20"},
                        "authenticationRef": {"name": "workload-identity"},
                    }
                ],
            },
        },
        sort_keys=False,
    )


def container_app_scale(min_replicas: int, http: bool) -> dict:
    rule = (
        {"name": "http", "http": {"metadata": {"concurrentRequests": "50"}}}
        if http
        else {
            "name": "queue",
            "custom": {
                "type": "azure-servicebus",
                "metadata": {"queueName": "dispatch-jobs", "messageCount": "20"},
            },
        }
    )
    return {"minReplicas": min_replicas, "maxReplicas": 10, "rules": [rule]}


def analyze() -> PatternResult:
    book = default_book()
    traffic = load_traffic()
    res = PatternResult(PATTERN, "Autoscale elastic apps (App Service, AKS, Container Apps)", [])
    for r in load_inventory():
        p = r["properties"]
        if r["type"].endswith("serverfarms") and p.get("profile") == "web-weekly" and not p.get("autoscale"):
            avg, peak = replay_app_service(traffic[f"{r['name']}.rps"], p["rps_per_instance"])
            unit = book.monthly(f"appservice.{r['sku']}")
            res.findings.append(
                Finding(
                    PATTERN,
                    r["id"],
                    r["name"],
                    f"autoscale {p['instances']} fixed -> {APP_MIN}..{APP_MAX} (avg {avg:.2f})",
                    unit * p["instances"],
                    unit * avg,
                    confidence="high",
                    risk="low",
                    change={
                        "op": "set-autoscale",
                        "profile": app_service_autoscale_profile(p["rps_per_instance"]),
                    },
                    evidence={
                        "fixed_instances": p["instances"],
                        "replayed_avg_instances": round(avg, 2),
                        "replayed_peak_instances": peak,
                        "rps_peak": max(traffic[f"{r['name']}.rps"]),
                        "rps_min": min(traffic[f"{r['name']}.rps"]),
                    },
                )
            )
        elif r["type"].endswith("managedClusters") and not p.get("autoscaler"):
            avg, peak = replay_aks(traffic[f"{r['name']}.pod_cores"])
            unit = book.monthly(vm_key(r["sku"]))
            res.findings.append(
                Finding(
                    PATTERN,
                    r["id"],
                    r["name"],
                    f"cluster autoscaler {p['node_count']} fixed -> {AKS_MIN}..{peak + 2} (avg {avg:.2f})",
                    unit * p["node_count"],
                    unit * avg,
                    confidence="high",
                    risk="low",
                    change={
                        "op": "enable-cluster-autoscaler",
                        "min": AKS_MIN,
                        "max": peak + 2,
                        "hpa": hpa_manifest("dispatch-worker"),
                    },
                    evidence={
                        "fixed_nodes": p["node_count"],
                        "replayed_avg_nodes": round(avg, 2),
                        "replayed_peak_nodes": peak,
                    },
                )
            )
        elif r["type"].endswith("containerApps") and p["min_replicas"] > 0 and p["active_fraction"] > 0:
            if r["tags"].get("env") == "prod":
                res.skipped.append(
                    (r["name"], "prod app with a latency objective; keeps minReplicas=1 by design")
                )
                continue
            before = monthly_cost(r, book)
            after = container_app_monthly(
                0, p["vcpu"], p["gib"], p["active_fraction"], p["monthly_requests"], book
            )
            http = not p.get("queue_driven")
            res.findings.append(
                Finding(
                    PATTERN,
                    r["id"],
                    r["name"],
                    f"scale to zero: minReplicas {p['min_replicas']} -> 0 ({'HTTP' if http else 'KEDA queue'})",
                    before,
                    after,
                    confidence="high",
                    risk="low",
                    change={
                        "op": "set-scale",
                        "scale": container_app_scale(0, http),
                        **({} if http else {"keda": keda_scaledobject(r["name"], "dispatch-jobs")}),
                    },
                    evidence={
                        "active_fraction": p["active_fraction"],
                        "min_replicas": p["min_replicas"],
                        "cold_start": "first request after idle waits for a replica (seconds)",
                    },
                )
            )
    res.notes.append(f"replayed one week of hourly demand; monthly = weekly average x {HOURS_PER_MONTH} h")
    return res
