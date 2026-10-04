"""Pattern 6: Azure Hybrid Benefit (AHB) for Windows Server and SQL Server licenses you already own.

With Software Assurance (or qualifying subscriptions), existing Windows Server and SQL Server core
licenses can be applied to Azure VMs, so the VM bills at the base (Linux) compute rate and the SQL
license meter drops to zero.

Assessment, simplified to the rules that drive most of the money (verify against your agreement):
  * Windows Server: every VM consumes max(8, vCPU) core licenses from the pool.
  * SQL Server: every VM consumes max(4, vCPU) core licenses of its edition.
  * Licenses are assigned greedily to the VMs with the highest monthly saving per core.
  * Run after rightsizing: a VM that is about to shrink is assessed at its target size.
"""

from __future__ import annotations

from typing import Any

from finops.costing import VM_SHAPES, sql_license_key
from finops.datasets import load_inventory, load_json
from finops.patterns import p01_rightsize
from finops.patterns.base import Finding, PatternResult
from finops.pricing import default_book, vm_key

PATTERN = "p06-hybrid-benefit"


def windows_cores(vcpu: int) -> int:
    return max(8, vcpu)


def sql_cores(vcpu: int) -> int:
    return max(4, vcpu)


def assign(candidates: list[dict[str, Any]], pool: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Greedy by saving per core, ties by name. Returns (covered, not covered)."""
    order = sorted(candidates, key=lambda c: (-c["saving"] / c["cores"], c["name"]))
    covered, left = [], []
    for c in order:
        if c["cores"] <= pool:
            pool -= c["cores"]
            covered.append(c)
        else:
            left.append(c)
    return covered, left


def analyze() -> PatternResult:
    book = default_book()
    ent = load_json("licenses/entitlements.json")
    targets = {
        f.resource_id: f.change["to"]
        for f in p01_rightsize.analyze().findings
        if f.change.get("kind") == "vm"
    }
    win, sql = [], []
    for r in load_inventory():
        p = r["properties"]
        if (
            not r["type"].endswith("virtualMachines")
            or p.get("os") != "windows"
            or p.get("power_state") != "running"
        ):
            continue
        size = targets.get(r["id"], r["sku"])
        vcpu = VM_SHAPES[size][0]
        if p.get("license_type") != "Windows_Server":
            win_saving = book.monthly(vm_key(size, "windows")) - book.monthly(vm_key(size, "linux"))
            win.append(
                {
                    "id": r["id"],
                    "name": r["name"],
                    "size": size,
                    "cores": windows_cores(vcpu),
                    "saving": win_saving,
                    "base": book.monthly(vm_key(size, "windows")),
                }
            )
        if p.get("sql_edition") and p.get("sql_license") != "ahb":
            key = sql_license_key(p["sql_edition"], vcpu)
            sql.append(
                {
                    "id": r["id"],
                    "name": r["name"],
                    "size": size,
                    "edition": p["sql_edition"],
                    "cores": sql_cores(vcpu),
                    "saving": book.monthly(key),
                    "base": book.monthly(key),
                }
            )
    res = PatternResult(PATTERN, "Azure Hybrid Benefit for owned Windows Server and SQL Server licenses", [])
    covered, left = assign(win, ent["windows_server_datacenter_cores_with_sa"])
    for c in covered:
        res.findings.append(
            Finding(
                PATTERN,
                c["id"],
                c["name"],
                f"AHB Windows Server ({c['cores']} cores) on {c['size']}",
                c["base"],
                c["base"] - c["saving"],
                change={"op": "set-license-type", "licenseType": "Windows_Server"},
                evidence={"cores_used": c["cores"], "size_assessed": c["size"]},
            )
        )
    for c in left:
        res.skipped.append((c["name"], f"no Windows Server cores left in the pool (needs {c['cores']})"))
    for edition in ("standard", "enterprise"):
        pool = ent[f"sql_{edition}_cores_with_sa"]
        cov, lft = assign([c for c in sql if c["edition"] == edition], pool)
        for c in cov:
            res.findings.append(
                Finding(
                    PATTERN,
                    c["id"],
                    c["name"],
                    f"AHB SQL Server {edition} ({c['cores']} cores)",
                    c["base"],
                    0.0,
                    change={"op": "set-sql-license", "sqlLicenseType": "AHUB"},
                    evidence={"cores_used": c["cores"], "edition": edition},
                )
            )
        for c in lft:
            res.skipped.append((c["name"], f"no SQL {edition} cores left (needs {c['cores']})"))
    res.notes.append(
        f"pool: {ent['windows_server_datacenter_cores_with_sa']} Windows Server cores, {ent['sql_standard_cores_with_sa']} SQL Standard cores, {ent['sql_enterprise_cores_with_sa']} SQL Enterprise cores (synthetic register)"
    )
    res.notes.append("savings are the license share of list price; sizes assessed after rightsizing (p01)")
    return res
