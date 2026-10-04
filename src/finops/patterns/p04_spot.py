"""Pattern 4: run interruptible batch work on Spot capacity, with checkpointing.

Spot VMs (Batch Spot nodes or VMSS Spot) cost a fraction of pay-as-you-go but can be evicted at
any time with about 30 seconds notice (Azure Scheduled Events, ``Preempt``). The pattern is only
worth it when the job can resume from a checkpoint and still meets its deadline.

Expected cost is simulated, not assumed: each run is replayed node by node with a seeded random
eviction process. The eviction rate is an ASSUMPTION (``EVICTION_RATE_PER_HOUR``), set to the
pessimistic end of the published eviction-rate bands; check the real band for your size and region
in the portal before trusting the result.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from finops.datasets import load_json
from finops.patterns.base import Finding, PatternResult, percentile
from finops.pricing import default_book, vm_key

PATTERN = "p04-spot"
EVICTION_RATE_PER_HOUR = 0.05  # ASSUMPTION: 5 % chance per node-hour
RESTART_MINUTES = 6.0  # replacement node allocation + container start
SIMULATED_RUNS = 400
SEED = 4


@dataclass
class SimResult:
    node_hours: float
    evictions: int
    wall_hours: float


def simulate_run(
    rng: random.Random, nodes: int, hours: float, checkpoint_min: float, rate: float = EVICTION_RATE_PER_HOUR
) -> SimResult:
    """Replay one run. Each node owns 1/nodes of the work. On eviction the node loses the work
    since its last checkpoint (all of it if checkpoint_min == 0) and pays a restart delay."""
    step = 1 / 60  # minute resolution
    p = rate * step
    total_hours, evictions, wall = 0.0, 0, 0.0
    for _ in range(nodes):
        done, since_ckpt, t = 0.0, 0.0, 0.0
        while done < hours:
            t += step
            done += step
            since_ckpt += step
            if checkpoint_min and since_ckpt * 60 >= checkpoint_min:
                since_ckpt = 0.0
            if rng.random() < p and done < hours:
                evictions += 1
                done -= since_ckpt if checkpoint_min else done
                since_ckpt = 0.0
                t += RESTART_MINUTES / 60
        total_hours += t
        wall = max(wall, t)
    return SimResult(total_hours, evictions, wall)


def evaluate(
    job: dict[str, Any], rate: float = EVICTION_RATE_PER_HOUR, checkpoint: bool = True
) -> dict[str, Any]:
    book = default_book()
    rng = random.Random(SEED)
    sims = [
        simulate_run(
            rng, job["nodes"], job["hours_per_run"], job["checkpoint_minutes"] if checkpoint else 0, rate
        )
        for _ in range(SIMULATED_RUNS)
    ]
    payg = book.price(vm_key(job["size"]))
    spot = book.price(vm_key(job["size"], offer="spot"))
    mean_hours = sum(s.node_hours for s in sims) / len(sims)
    walls = [s.wall_hours for s in sims]
    return {
        "payg_monthly": round(job["nodes"] * job["hours_per_run"] * payg * job["runs_per_month"], 2),
        "spot_monthly": round(mean_hours * spot * job["runs_per_month"], 2),
        "rework_pct": round(100 * (mean_hours / (job["nodes"] * job["hours_per_run"]) - 1), 1),
        "evictions_per_run": round(sum(s.evictions for s in sims) / len(sims), 2),
        "wall_p95_hours": round(percentile(walls, 95), 2),
        "deadline_hours": job["deadline_hours"],
        "spot_discount_pct": round(100 * (1 - spot / payg), 1),
    }


def analyze() -> PatternResult:
    res = PatternResult(PATTERN, "Spot capacity for interruptible batch work", [])
    for job in load_json("batch/jobs.json"):
        if not job["interruptible"]:
            res.skipped.append(
                (
                    job["name"],
                    "not interruptible (financial close must finish in one pass); stays on pay-as-you-go",
                )
            )
            continue
        ev = evaluate(job)
        no_ckpt = evaluate(job, checkpoint=False)
        ev["without_checkpoint"] = {
            "spot_monthly": round(no_ckpt["spot_monthly"], 2),
            "wall_p95_hours": no_ckpt["wall_p95_hours"],
            "rework_pct": no_ckpt["rework_pct"],
        }
        if ev["wall_p95_hours"] > job["deadline_hours"]:
            res.skipped.append(
                (
                    job["name"],
                    f"p95 completion {ev['wall_p95_hours']} h misses the {job['deadline_hours']} h deadline on Spot",
                )
            )
            continue
        res.findings.append(
            Finding(
                PATTERN,
                f"batch-lk-prod/pools/{job['name']}",
                f"pool:{job['name']}",
                f"Spot nodes, checkpoint every {job['checkpoint_minutes']} min ({job['nodes']}x {job['size']})",
                ev["payg_monthly"],
                ev["spot_monthly"],
                confidence="medium",
                risk="low",
                change={
                    "op": "pool-priority",
                    "to": "spot",
                    "fallback": "dedicated",
                    "eviction_policy": "Delete",
                    "checkpoint_minutes": job["checkpoint_minutes"],
                },
                evidence=ev,
                estimate=True,
            )
        )
    res.notes.append(
        f"ASSUMPTION eviction rate {EVICTION_RATE_PER_HOUR:.0%}/node-hour, restart {RESTART_MINUTES:.0f} min, {SIMULATED_RUNS} simulated runs per job (seed {SEED})"
    )
    for f in res.findings:
        w = f.evidence["without_checkpoint"]
        res.notes.append(
            f"{f.resource_name}: rework {f.evidence['rework_pct']}% with checkpoints vs {w['rework_pct']}% without; p95 wall {f.evidence['wall_p95_hours']} h vs {w['wall_p95_hours']} h"
        )
    return res


# ------------------------------------------------------------------ eviction handling, runnable
@dataclass
class CheckpointStore:
    """Stand-in for a blob container that holds one checkpoint per job."""

    data: dict[str, dict[str, Any]] = field(default_factory=dict)

    def save(self, job: str, step: int, state: Any) -> None:
        self.data[job] = {"step": step, "state": state}

    def load(self, job: str) -> tuple[int, Any]:
        c = self.data.get(job)
        return (c["step"], c["state"]) if c else (0, None)


class Preempted(Exception):
    pass


def run_resumable(
    job: str,
    steps: list[Callable[[Any], Any]],
    store: CheckpointStore,
    preempt_at: set[int] | None = None,
    checkpoint_every: int = 1,
    initial: Any = 0,
) -> Any:
    """Run ``steps`` in order, resuming from the store. ``preempt_at`` simulates an Azure Scheduled
    Events ``Preempt`` notice arriving before the given step: the worker checkpoints and exits."""
    start, state = store.load(job)
    if state is None:
        state = initial
    for i in range(start, len(steps)):
        if preempt_at and i in preempt_at:
            preempt_at.discard(i)
            store.save(job, i, state)  # the ~30 s notice is enough to flush a small checkpoint
            raise Preempted(f"preempted before step {i}")
        state = steps[i](state)
        if (i + 1) % checkpoint_every == 0:
            store.save(job, i + 1, state)
    store.save(job, len(steps), state)
    return state


def run_until_done(
    job: str,
    steps: list[Callable[[Any], Any]],
    store: CheckpointStore,
    preempt_at: set[int],
    max_attempts: int = 10,
) -> tuple[Any, int]:
    for attempt in range(1, max_attempts + 1):
        try:
            return run_resumable(job, steps, store, preempt_at), attempt
        except Preempted:
            continue
    raise RuntimeError("gave up after repeated evictions; fall back to dedicated nodes")
