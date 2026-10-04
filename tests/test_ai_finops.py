"""AI FinOps: attribution, routing, caching, budgets, PTU, ROI and the eval gate."""

import pytest

from finops.ai import caching, ptu, roi, routing
from finops.ai.budgets import enforce
from finops.ai.eval_gate import Candidate, gate
from finops.ai.report import analyze, report
from finops.ai.token_cost import attribute, cached_prefix_tokens, reconcile, request_cost
from finops.datasets import load_ai_requests, load_json

REQ = {
    "request_id": "r1",
    "tenant": "t",
    "agent": "eta-assistant",
    "use_case": "u",
    "prompt": "where is shipment 1001",
    "day": 1,
    "system_prefix_tokens": 1280,
    "prompt_tokens": 1500,
    "completion_tokens": 100,
    "label": "simple",
    "model": "gpt-4o",
    "weight": 1,
}


@pytest.fixture(scope="module")
def a():
    return analyze()


def test_request_cost_math():
    assert request_cost(REQ) == pytest.approx((1500 * 0.0025 + 100 * 0.01) / 1000)
    assert request_cost(REQ, "gpt-4o-mini") == pytest.approx((1500 * 0.00015 + 100 * 0.0006) / 1000)


def test_prompt_cache_bills_prefix_at_cached_rate():
    saved = request_cost(REQ) - request_cost(REQ, prompt_cache=True)
    assert saved == pytest.approx(1280 * (0.0025 - 0.00125) / 1000)


def test_prompt_cache_threshold():
    assert (
        cached_prefix_tokens(1000) == 0
        and cached_prefix_tokens(1100) == 1024
        and cached_prefix_tokens(1280) == 1280
    )


def test_attribution_reconciles_to_the_bill(a):
    assert a["reconcile"]["ok"] and a["reconcile"]["gap"] == 0


def test_attribution_sums_by_every_dimension(a):
    att = a["attribution"]
    for k in ("by_tenant", "by_agent", "by_use_case"):
        assert sum(att[k].values()) == pytest.approx(att["total"])


def test_reconcile_flags_gaps():
    assert not reconcile(110, 100)["ok"] and reconcile(100.5, 100)["ok"]


def test_classifier_routes_obvious_cases():
    assert routing.classify("where is shipment 1001")[0] == routing.SMALL
    assert routing.classify("review the proof of delivery notes and draft a reply")[0] == routing.LARGE


def test_classifier_fails_safe_to_large_model():
    route, conf = routing.classify("can you tell me whether the delivery for order 1001 still arrives today")
    assert route == routing.LARGE and conf == 0.5


def test_router_misroutes_only_the_tricky_prompt(a):
    assert a["routing_confusion"]["complex->small"] > 0
    for q in load_ai_requests():
        if q["label"] == "complex" and routing.route(q) == routing.SMALL:
            assert "strike" in q["prompt"]


def test_quality_simulation_is_deterministic():
    assert routing.passes(REQ, routing.LARGE) == routing.passes(REQ, routing.LARGE)


def test_cache_never_crosses_tenants():
    c = caching.ResponseCache()
    assert c.lookup(REQ) == "miss"
    assert c.lookup({**REQ, "request_id": "r2"}) == "exact"
    assert c.lookup({**REQ, "request_id": "r3", "tenant": "other"}) == "miss"


def test_semantic_hit_needs_same_entity():
    c = caching.ResponseCache()
    c.lookup(REQ)
    assert c.lookup({**REQ, "prompt": "track parcel 1001"}) == "semantic"
    assert c.lookup({**REQ, "prompt": "track parcel 1002"}) == "miss"


def test_cache_entries_expire():
    c = caching.ResponseCache(ttl_days=1)
    c.lookup(REQ)
    assert c.lookup({**REQ, "day": 2}) == "miss"


def test_complex_requests_are_never_cached():
    c = caching.ResponseCache()
    q = {**REQ, "label": "complex"}
    assert c.lookup(q) == "miss" and c.lookup(q) == "miss"


def test_loose_threshold_serves_wrong_answers(a):
    assert a["loose_cache_wrong"] > 0


def test_eval_gate_blocks_quality_drop():
    base = Candidate("b", 100, 95.0)
    assert not gate(base, Candidate("c", 10, 90.0)).ship
    assert gate(base, Candidate("c", 80, 94.5)).ship
    assert not gate(base, Candidate("c", 80, 95.0, safety_regressions=1)).ship
    assert not gate(base, Candidate("c", 120, 96.0)).ship


def test_gate_decisions_on_real_candidates(a):
    d = {x.name: x for x in a["decisions"]}
    assert not d["everything on gpt-4o-mini"].ship
    assert not d["semantic cache, loose threshold 0.45"].ship
    assert d["combined: route + prompt cache + response cache"].ship
    assert d["combined: route + prompt cache + response cache"].savings == 200.75


def test_budget_guard_degrades_then_blocks():
    reqs = [{**REQ, "request_id": f"r{i}", "day": 1 + i // 100, "weight": 100} for i in range(300)]
    cfg = {
        "tenant_monthly_usd": {"t": 10.0},
        "agent_monthly_usd": {"eta-assistant": 100.0},
        "soft_alert": 0.8,
        "degrade_at": 1.0,
        "block_at": 1.2,
        "critical_agents": [],
    }
    g = enforce(reqs, cfg)
    assert g["counts"]["degraded"] > 0 and g["counts"]["blocked"] > 0
    assert any("120%" in x for x in g["alerts"])


def test_critical_agents_are_never_blocked():
    reqs = [{**REQ, "agent": "invoice-triage", "request_id": f"r{i}", "weight": 1000} for i in range(200)]
    cfg = {
        "tenant_monthly_usd": {"t": 1.0},
        "agent_monthly_usd": {"invoice-triage": 1.0},
        "soft_alert": 0.8,
        "degrade_at": 1.0,
        "block_at": 1.2,
        "critical_agents": ["invoice-triage"],
    }
    g = enforce(reqs, cfg)
    assert g["counts"]["blocked"] == 0 and g["counts"]["critical_over_budget"] > 0


def test_budget_guard_on_the_log(a):
    assert a["budget_guard"]["total"] < a["baseline"].monthly_cost
    assert set(load_json("ai/budgets.json")["critical_agents"]) == {"invoice-triage"}


def test_ptu_sizing_rules():
    assert ptu.ptus_for(0) == 15 and ptu.ptus_for(15 * 2500 + 1) == 20


def test_ptu_does_not_pay_at_this_volume(a):
    p = a["ptu"]
    assert p["ptus"] == 15 and p["ptu_monthly"] == 10950.0 and p["decision"].startswith("stay pay-as-you-go")


def test_roi_math():
    uc = {
        "use_case": "x",
        "minutes_saved_per_task": 6,
        "loaded_rate_per_hour": 60,
        "adoption": 0.5,
        "build_cost": 1200,
        "amortize_months": 12,
        "platform_monthly": 50,
    }
    r = roi.roi(uc, 1000, 50)
    assert (
        r["value"] == 3000
        and r["total_cost"] == 200
        and r["roi_pct"] == 1400.0
        and r["payback_months"] == 0.4
    )


def test_roi_flags_a_use_case_to_rework(a):
    verdicts = {x["after"]["use_case"]: x["after"]["verdict"] for x in a["roi"]}
    assert verdicts["dispatch-shift-summary"] == "rework or retire"


def test_report_renders(a):
    text = report(a)
    assert "eval gate" in text and "BLOCK" in text and "SHIP" in text


def test_attribute_with_model_override():
    reqs = load_ai_requests()[:100]
    assert attribute(reqs, lambda q: "gpt-4o-mini")["total"] < attribute(reqs)["total"]
