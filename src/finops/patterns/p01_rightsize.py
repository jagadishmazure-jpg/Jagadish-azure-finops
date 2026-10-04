"""Pattern 1: rightsize compute to measured demand (VMs and App Service plans).

Decision rule (all thresholds in ``RULE``):
  * at least 14 days of hourly CPU and memory metrics;
  * candidate if p95 CPU < 40 % AND p95 memory < 50 %;
  * step down one size at a time inside the same family while the PROJECTED p95 CPU stays
    <= 65 % and projected p95 memory <= 75 % (load scales with the capacity ratio);
  * if the projected PEAK exceeds 100 % the finding is kept but marked medium confidence /
    medium risk (a periodic spike would saturate the smaller size).
"""

from __future__ import annotations

from finops.costing import VM_SHAPES, monthly_cost
from finops.datasets import load_inventory, load_utilization
from finops.patterns.base import Finding, PatternResult, percentile
from finops.pricing import default_book

PATTERN = "p01-rightsize"
RULE = {"min_hours": 14 * 24, "cpu_p95_max": 40.0, "mem_p95_max": 50.0, "target_cpu_p95": 65.0, "target_mem_p95": 75.0}
VM_LADDER = {"Dsv5": ["D2s_v5", "D4s_v5", "D8s_v5"], "Esv5": ["E4s_v5"]}
PLAN_LADDER = ["P0v3", "P1v3", "P2v3", "P3v3"]
PLAN_SHAPES = {"P0v3": (1, 4), "P1v3": (2, 8), "P2v3": (4, 16), "P3v3": (8, 32)}


def _family(size: str) -> list[str]:
    for sizes in VM_LADDER.values():
        if size in sizes:
            return sizes
    return [size]


def recommend(size: str, ladder: list[str], shapes: dict, cpu: list[float], mem: list[float]) -> tuple[str, dict]:
    """Return (target size, evidence). Target == size means no change."""
    p95c, p95m, peak = percentile(cpu, 95), percentile(mem, 95), max(cpu)
    ev = {"cpu_p95": p95c, "mem_p95": p95m, "cpu_peak": peak, "hours": len(cpu)}
    if len(cpu) < RULE["min_hours"]:
        ev["reason"] = f"only {len(cpu)} h of metrics (< {RULE['min_hours']})"
        return size, ev
    if p95c >= RULE["cpu_p95_max"] or p95m >= RULE["mem_p95_max"]:
        ev["reason"] = f"p95 CPU {p95c}% / memory {p95m}% above the candidate thresholds"
        return size, ev
    target = size
    idx = ladder.index(size)
    while idx > 0:
        cand = ladder[idx - 1]
        rc = shapes[size][0] / shapes[cand][0]
        rm = shapes[size][1] / shapes[cand][1]
        if p95c * rc > RULE["target_cpu_p95"] or p95m * rm > RULE["target_mem_p95"]:
            break
        target, idx = cand, idx - 1
    if target == size:
        ev["reason"] = "already the smallest size that keeps projected p95 within target" if idx else "smallest size in the family ladder"
        return size, ev
    rc = shapes[size][0] / shapes[target][0]
    ev.update(projected_cpu_p95=round(p95c * rc, 1), projected_mem_p95=round(p95m * shapes[size][1] / shapes[target][1], 1),
              projected_cpu_peak=round(peak * rc, 1))
    return target, ev


def analyze() -> PatternResult:
    book = default_book()
    util = load_utilization()
    res = PatternResult(PATTERN, "Rightsize compute to measured demand", [])
    for r in load_inventory():
        is_vm = r["type"].endswith("virtualMachines")
        is_plan = r["type"].endswith("serverfarms") and r["sku"] in PLAN_SHAPES
        if not (is_vm or is_plan):
            continue
        p = r["properties"]
        if is_vm and p.get("power_state") != "running":
            res.skipped.append((r["name"], f"VM is {p.get('power_state')}; handled by idle cleanup (p08)"))
            continue
        if is_plan and p.get("apps", 1) == 0:
            res.skipped.append((r["name"], "plan hosts 0 apps; handled by idle cleanup (p08)"))
            continue
        if r["id"] not in util:
            res.skipped.append((r["name"], "no utilization metrics (elastic plan; see autoscale p02)"))
            continue
        m = util[r["id"]]
        ladder, shapes = (_family(r["sku"]), VM_SHAPES) if is_vm else (PLAN_LADDER, PLAN_SHAPES)
        target, ev = recommend(r["sku"], ladder, shapes, m["cpu"], m["mem"])
        if target == r["sku"]:
            res.skipped.append((r["name"], ev["reason"]))
            continue
        after = {**r, "sku": target}
        burst = ev["projected_cpu_peak"] > 100
        res.findings.append(Finding(
            PATTERN, r["id"], r["name"], f"resize {r['sku']} -> {target}",
            monthly_cost(r, book), monthly_cost(after, book),
            confidence="medium" if burst else "high", risk="medium" if burst else "low",
            change={"op": "resize", "from": r["sku"], "to": target, "kind": "vm" if is_vm else "app-service-plan"},
            evidence=ev,
        ))
        if burst:
            res.notes.append(f"{r['name']}: projected peak {ev['projected_cpu_peak']}% > 100%; resize after moving the weekly spike or accept queuing")
    return res
