"""Pattern 8: find and remove idle and orphaned resources, with a human approval gate.

Detectors (each mirrors an Azure Resource Graph query in ``queries/arg/``):
  * unattached managed disks older than the grace period -> snapshot, then delete;
  * public IPs not associated with anything older than the grace period -> delete;
  * network interfaces attached to nothing -> delete (free, but clutter and IP exhaustion);
  * App Service / Logic Apps plans hosting no apps, or with zero runs -> delete plan;
  * VMs stopped but not deallocated (compute still bills) -> deallocate;
  * VMs deallocated for a long time -> flag for owner review (disks still bill);
  * Container Apps with a warm replica and zero traffic -> minReplicas 0.

Nothing is deleted here. The agent turns findings into a dry-run plan that needs an approval
(``finops.agent.approval``). Resources tagged ``finops-exempt=true`` are never proposed.
"""

from __future__ import annotations

from typing import Any

from finops.costing import container_app_monthly, monthly_cost
from finops.datasets import load_inventory
from finops.patterns.base import Finding, PatternResult
from finops.pricing import PriceBook, default_book

PATTERN = "p08-idle-cleanup"
GRACE_DAYS = {"disk": 30, "pip": 7}


def detect(inventory: list[dict[str, Any]], book: PriceBook | None = None, pattern: str = PATTERN) -> PatternResult:
    book = book or default_book()
    res = PatternResult(pattern, "Idle and orphaned resource cleanup (approval required)", [])
    plans_with_running_apps = {r["properties"].get("plan") for r in inventory if r["properties"].get("monthly_runs", 0) > 0}
    for r in inventory:
        t, p, name = r["type"], r["properties"], r["name"]
        if r["tags"].get("finops-exempt") == "true":
            res.skipped.append((name, "tagged finops-exempt=true"))
            continue
        f = None
        if t.endswith("disks") and p.get("disk_state") == "Unattached":
            if p["days_unattached"] < GRACE_DAYS["disk"]:
                res.skipped.append((name, f"unattached {p['days_unattached']} d (< {GRACE_DAYS['disk']} d grace)"))
                continue
            f = Finding(pattern, r["id"], name, f"snapshot + delete unattached {r['sku']} disk ({p['days_unattached']} d)",
                        monthly_cost(r, book), 0.0, change={"op": "delete", "pre": "snapshot"}, reversible=False,
                        evidence={"days_unattached": p["days_unattached"], "size_gb": p["size_gb"]})
        elif t.endswith("publicIPAddresses") and not p.get("associated", True):
            if p["days_unassociated"] < GRACE_DAYS["pip"]:
                res.skipped.append((name, f"unassociated {p['days_unassociated']} d (< {GRACE_DAYS['pip']} d grace)"))
                continue
            f = Finding(pattern, r["id"], name, f"delete unassociated public IP ({p['days_unassociated']} d)",
                        monthly_cost(r, book), 0.0, change={"op": "delete"}, reversible=False, evidence={"days_unassociated": p["days_unassociated"]})
        elif t.endswith("networkInterfaces") and not p.get("attached", True):
            f = Finding(pattern, r["id"], name, "delete orphaned NIC (hygiene, $0)", 0.0, 0.0, change={"op": "delete"}, reversible=False)
        elif t.endswith("serverfarms") and (p.get("apps") == 0 or (p.get("kind") == "workflowapp-plan" and p.get("workflow_runs_30d") == 0)):
            idle_reason = "0 apps" if p.get("apps") == 0 else f"0 workflow runs in 30 d (last run {p.get('last_run_days_ago')} d ago)"
            f = Finding(pattern, r["id"], name, f"delete idle {r['sku']} plan ({idle_reason})", monthly_cost(r, book), 0.0,
                        change={"op": "delete", "pre": "export-config"}, reversible=False, evidence={"reason": idle_reason})
            if r["id"] in plans_with_running_apps:
                f = None
        elif t.endswith("virtualMachines") and p.get("power_state") == "stopped":
            f = Finding(pattern, r["id"], name, "deallocate VM stopped but still billing compute", monthly_cost(r, book), 0.0,
                        change={"op": "deallocate"}, evidence={"power_state": "stopped (not deallocated)"})
        elif t.endswith("virtualMachines") and p.get("power_state") == "deallocated":
            res.skipped.append((name, "deallocated: compute is already $0; owner review for disks"))
            continue
        elif t.endswith("containerApps") and p["min_replicas"] > 0 and p["active_fraction"] == 0 and p["monthly_requests"] == 0:
            after = container_app_monthly(0, p["vcpu"], p["gib"], 0, 0, book)
            f = Finding(pattern, r["id"], name, f"minReplicas {p['min_replicas']} -> 0 (zero requests in 30 d)", monthly_cost(r, book), after,
                        change={"op": "set-scale", "minReplicas": 0}, evidence={"requests_30d": 0, "min_replicas": p["min_replicas"]})
        if f:
            res.findings.append(f)
    return res


def analyze() -> PatternResult:
    res = detect(load_inventory())
    res.notes.append(f"grace periods: disks {GRACE_DAYS['disk']} d, public IPs {GRACE_DAYS['pip']} d; every action needs an approved plan")
    return res
