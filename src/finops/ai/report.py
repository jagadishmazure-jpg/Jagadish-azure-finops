"""AI FinOps end to end on the synthetic request log: attribute, optimize, gate, budget, PTU, ROI."""

from __future__ import annotations

from collections import Counter
from typing import Any

from finops.ai import caching, ptu, roi, routing
from finops.ai.budgets import enforce
from finops.ai.eval_gate import Candidate, gate
from finops.ai.token_cost import attribute, reconcile, request_cost
from finops.datasets import load_ai_requests, load_focus, load_json
from finops.patterns.base import money

LOOSE_THRESHOLD = 0.45  # deliberately too loose: shows why the eval gate exists


def _cost(reqs, model_for=None, prompt_cache=False, skip: set[str] | None = None) -> float:
    skip = skip or set()
    return sum(
        request_cost(q, model_for(q) if model_for else None, prompt_cache) * q["weight"]
        for q in reqs
        if q["request_id"] not in skip
    )


def _quality(reqs, model_for, hits: set[str] | None = None, wrong: set[str] | None = None) -> float:
    hits, wrong = hits or set(), wrong or set()
    ok = 0
    for q in reqs:
        if q["request_id"] in hits:
            ok += q["request_id"] not in wrong
        else:
            ok += routing.passes(q, model_for(q))
    return round(100 * ok / len(reqs), 2)


def analyze() -> dict[str, Any]:
    reqs = load_ai_requests()
    base_model = lambda q: q["model"]  # noqa: E731
    all_small = lambda q: routing.SMALL  # noqa: E731
    base = attribute(reqs)
    billed = sum(r.cost for r in load_focus() if r.service == "Foundry Models")
    cache = caching.simulate(reqs)
    loose = caching.simulate(reqs, threshold=LOOSE_THRESHOLD)

    baseline = Candidate("baseline (all gpt-4o)", _cost(reqs), _quality(reqs, base_model))
    cands = [
        Candidate("route simple -> gpt-4o-mini", _cost(reqs, routing.route), _quality(reqs, routing.route)),
        Candidate("provider prompt caching", _cost(reqs, prompt_cache=True), _quality(reqs, base_model)),
        Candidate(
            "response cache (exact + semantic 0.85)",
            _cost(reqs, skip=cache["hit_ids"]),
            _quality(reqs, base_model, cache["hit_ids"], cache["wrong_ids"]),
        ),
        Candidate(
            f"semantic cache, loose threshold {LOOSE_THRESHOLD}",
            _cost(reqs, skip=loose["hit_ids"]),
            _quality(reqs, base_model, loose["hit_ids"], loose["wrong_ids"]),
        ),
        Candidate("everything on gpt-4o-mini", _cost(reqs, all_small), _quality(reqs, all_small)),
        Candidate(
            "combined: route + prompt cache + response cache",
            _cost(reqs, routing.route, True, cache["hit_ids"]),
            _quality(reqs, routing.route, cache["hit_ids"], cache["wrong_ids"]),
        ),
    ]
    decisions = [gate(baseline, c) for c in cands]
    combined = cands[-1]

    in_tok = sum(q["prompt_tokens"] * q["weight"] for q in reqs)
    out_tok = sum(q["completion_tokens"] * q["weight"] for q in reqs)
    ptu_view = ptu.analyze(in_tok, out_tok, baseline.monthly_cost)

    budgets = load_json("ai/budgets.json")
    guard = enforce(reqs, budgets)

    opt_by_uc = attribute(
        [q for q in reqs if q["request_id"] not in cache["hit_ids"]], routing.route, prompt_cache=True
    )["by_use_case"]
    tasks = Counter()
    for q in reqs:
        tasks[q["use_case"]] += q["weight"]
    rois = []
    for uc in load_json("ai/use-cases.json"):
        before = roi.roi(uc, tasks[uc["use_case"]], base["by_use_case"][uc["use_case"]])
        after = roi.roi(uc, tasks[uc["use_case"]], opt_by_uc.get(uc["use_case"], 0.0))
        rois.append({"before": before, "after": after})
    return {
        "attribution": base,
        "reconcile": reconcile(base["total"], billed),
        "routing_confusion": routing.confusion(reqs),
        "cache": {k: v for k, v in cache.items() if not k.endswith("_ids")},
        "loose_cache_wrong": len(loose["wrong_ids"]),
        "baseline": baseline,
        "candidates": cands,
        "decisions": decisions,
        "combined": combined,
        "ptu": ptu_view,
        "budget_guard": guard,
        "roi": rois,
    }


def report(a: dict[str, Any] | None = None) -> str:
    a = a or analyze()
    att = a["attribution"]
    L = ["== ai-finops: token cost attribution, routing, caching, budgets, PTU, ROI"]
    L.append(
        f"  requests/month {att['requests']:,}  cost {money(att['total'])}  per request p50 ${att['per_request_p50']:.4f} p95 ${att['per_request_p95']:.4f}"
    )
    r = a["reconcile"]
    L.append(
        f"  reconcile to FOCUS bill: attributed {money(r['attributed'])} vs billed {money(r['billed'])} gap {money(r['gap'])} -> {'OK' if r['ok'] else 'MISMATCH'}"
    )
    for k in ("by_tenant", "by_agent", "by_use_case"):
        L.append(f"  {k}: " + ", ".join(f"{n} {money(v)}" for n, v in att[k].items()))
    L.append(f"  router confusion (label->route): {a['routing_confusion']}")
    c = a["cache"]
    L.append(
        f"  response cache: {c['exact']} exact + {c['semantic']} semantic hits of {c['exact'] + c['semantic'] + c['miss']} requests ({c['hit_rate']}%); loose threshold serves {a['loose_cache_wrong']} wrong answers"
    )
    b = a["baseline"]
    L.append(f"  eval gate (max quality drop 1.0 pt) vs baseline {money(b.monthly_cost)} @ {b.quality_pct}%:")
    for cand, d in zip(a["candidates"], a["decisions"], strict=True):
        L.append(
            f"    {'SHIP ' if d.ship else 'BLOCK'} {cand.name:<48} {money(cand.monthly_cost):>9}  quality {cand.quality_pct:>6}% ({d.quality_delta:+.2f})  save {money(d.savings):>9}  {d.reason}"
        )
    p = a["ptu"]
    L.append(
        f"  PTU: peak {p['peak_tpm']:,} TPM -> {p['ptus']} PTU = {money(p['ptu_monthly'])}/mo vs PAYG {money(p['payg_monthly'])}/mo; utilization {p['utilization_pct']}%; "
        f"break-even at {p['breakeven_volume_multiple']}x today's volume ({p['breakeven_utilization_pct']}% utilization) -> {p['decision']}"
    )
    g = a["budget_guard"]
    L.append(
        f"  budget guardrails: {g['counts']} -> spend {money(g['total'])} (from {money(b.monthly_cost)})"
    )
    for line in g["alerts"]:
        L.append(f"    {line}")
    L.append("  ROI per use case (before -> after the shipped optimizations):")
    for x in a["roi"]:
        bf, af = x["before"], x["after"]
        L.append(
            f"    {bf['use_case']:<26} tasks {bf['tasks']:>6,}  value {money(bf['value']):>10}  cost {money(bf['total_cost']):>9} -> {money(af['total_cost']):>9}  "
            f"ROI {bf['roi_pct']:>6}% -> {af['roi_pct']:>6}%  payback {bf['payback_months']} -> {af['payback_months']} mo  [{af['verdict']}]"
        )
    return "\n".join(L)
