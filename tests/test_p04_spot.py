import random

import pytest
from tests.conftest import find

from finops.patterns import p04_spot as P


@pytest.fixture(scope="module")
def res():
    return P.analyze()


def test_non_interruptible_job_stays_on_payg(res):
    assert any(n == "month-end-close" for n, _ in res.skipped)


def test_spot_findings_are_marked_estimates(res):
    assert res.findings and all(f.estimate for f in res.findings)


def test_checkpointing_reduces_rework(res):
    for f in res.findings:
        assert f.evidence["rework_pct"] < f.evidence["without_checkpoint"]["rework_pct"]


def test_deadline_is_respected(res):
    for f in res.findings:
        assert f.evidence["wall_p95_hours"] <= f.evidence["deadline_hours"]


def test_no_evictions_means_no_rework():
    r = P.simulate_run(random.Random(1), nodes=3, hours=2.0, checkpoint_min=15, rate=0.0)
    assert r.evictions == 0 and r.node_hours == pytest.approx(6.0, abs=0.05)


def test_job_that_misses_deadline_is_rejected(monkeypatch):
    jobs = [
        {
            "name": "tight",
            "size": "D4s_v5",
            "nodes": 2,
            "hours_per_run": 4.0,
            "runs_per_month": 1,
            "interruptible": True,
            "checkpoint_minutes": 30,
            "deadline_hours": 4.0,
        }
    ]
    monkeypatch.setattr(P, "load_json", lambda _: jobs)
    out = P.analyze()
    assert not out.findings and "deadline" in out.skipped[0][1]


def test_resume_after_preemption_gives_same_result():
    steps = [lambda s, i=i: s + i for i in range(10)]
    clean = P.run_resumable("j", steps, P.CheckpointStore())
    store = P.CheckpointStore()
    result, attempts = P.run_until_done("j", steps, store, preempt_at={3, 7})
    assert result == clean == 45 and attempts == 3


def test_checkpoint_store_starts_empty():
    assert P.CheckpointStore().load("x") == (0, None)


def test_route_optimizer_headline(res):
    assert find(res, "pool:route-optimizer").savings_monthly == 233.64
