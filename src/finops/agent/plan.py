"""Change plans: findings -> ordered dry-run steps with a content hash that approvals bind to."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from finops.patterns.base import Finding


def _rg_name(resource_id: str) -> tuple[str, str]:
    if "/resourceGroups/" not in resource_id:
        return "", resource_id
    rg = resource_id.split("/resourceGroups/")[1].split("/")[0]
    return rg, resource_id.rsplit("/", 1)[-1]


def az_command(f: Finding) -> str:
    """The Azure CLI command a human would run. Never executed by this repo."""
    rg, name = _rg_name(f.resource_id)
    c = f.change
    op = c.get("op")
    if op == "resize":
        if c.get("kind") == "vm":
            return f"az vm resize -g {rg} -n {name} --size Standard_{c['to']}"
        return f"az appservice plan update -g {rg} -n {name} --sku {c['to'].upper()}"
    if op == "deallocate":
        return f"az vm deallocate -g {rg} -n {name}"
    if op == "delete":
        if "/disks/" in f.resource_id:
            return f"az snapshot create -g {rg} -n {name}-final --source {name} && az disk delete -g {rg} -n {name} --yes"
        if "/publicIPAddresses/" in f.resource_id:
            return f"az network public-ip delete -g {rg} -n {name}"
        if "/networkInterfaces/" in f.resource_id:
            return f"az network nic delete -g {rg} -n {name}"
        if "/serverfarms/" in f.resource_id:
            return f"az appservice plan delete -g {rg} -n {name} --yes  # delete or move any (idle) apps on the plan first"
        return f"az resource delete --ids {f.resource_id}"
    if op == "set-scale":
        return f"az containerapp update -g {rg} -n {name} --min-replicas 0"
    if op == "set-license-type":
        return f"az vm update -g {rg} -n {name} --license-type Windows_Server"
    if op == "set-sql-license":
        return f"az sql vm update -g {rg} -n {name} --license-type AHUB"
    if op == "set-autoscale":
        p = c["profile"]["capacity"]
        return f"az monitor autoscale create -g {rg} --resource {name} --resource-type Microsoft.Web/serverfarms --min-count {p['minimum']} --max-count {p['maximum']} --count {p['default']}"
    if op == "enable-cluster-autoscaler":
        return f"az aks nodepool update -g {rg} --cluster-name {name} -n nodepool1 --enable-cluster-autoscaler --min-count {c['min']} --max-count {c['max']}"
    if op == "tag":
        return f"az tag update --resource-id <id of {f.resource_name}> --operation merge --tags cost-center=<from rg map>"
    if op == "lifecycle-policy":
        return f"az storage account management-policy create --account-name {f.resource_name.split('/')[0]} -g <rg> --policy @lifecycle-policy.json"
    if op == "purchase-commitment":
        return f"# finance purchase: {c['type']} x{c['quantity']} {c['sku']} (portal or az reservations), scope {c['scope']}"
    return f"# change via infrastructure-as-code pull request: {f.action}"


ROLLBACK = {
    "resize": "resize back to the original size",
    "deallocate": "az vm start",
    "delete": "restore from the final snapshot / exported config (not a true undo)",
    "set-scale": "set --min-replicas back to the previous value",
    "set-license-type": "az vm update --license-type None",
    "set-sql-license": "az sql vm update --license-type PAYG",
    "set-autoscale": "delete the autoscale setting and set the fixed count",
    "enable-cluster-autoscaler": "disable the autoscaler and set the node count",
    "purchase-commitment": "exchange or cancel within the reservation policy limits (fees may apply)",
}


@dataclass
class Step:
    finding_id: str
    resource: str
    action: str
    command: str
    rollback: str
    reversible: bool
    savings_monthly: float


@dataclass
class ChangePlan:
    plan_id: str
    requested_by: str
    steps: list[Step]
    status: str = "awaiting-approval"
    log: list[str] = field(default_factory=list)

    @property
    def irreversible(self) -> bool:
        return any(not s.reversible for s in self.steps)

    @property
    def savings_monthly(self) -> float:
        return round(sum(s.savings_monthly for s in self.steps), 2)

    def content(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "requested_by": self.requested_by,
            "steps": [s.__dict__ for s in self.steps],
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(json.dumps(self.content(), sort_keys=True).encode()).hexdigest()


def plan_from_content(content: dict[str, Any]) -> ChangePlan:
    return ChangePlan(content["plan_id"], content["requested_by"], [Step(**s) for s in content["steps"]])


def build_plan(findings: list[Finding], requested_by: str = "finops-agent") -> ChangePlan:
    steps = [
        Step(
            f.id,
            f.resource_name,
            f.action,
            az_command(f),
            ROLLBACK.get(f.change.get("op", ""), "revert the IaC change"),
            f.reversible,
            f.savings_monthly,
        )
        for f in findings
    ]
    pid = "plan-" + hashlib.sha256("|".join(s.finding_id for s in steps).encode()).hexdigest()[:10]
    return ChangePlan(pid, requested_by, steps)
