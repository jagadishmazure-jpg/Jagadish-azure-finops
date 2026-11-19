"""Single-model vs routed cost on the published GPT-6.2 rates.

Foundry's model router picks among 44 models and does not publish those prices. This simulation
is a two-tier stand-in for that idea: the existing fail-safe classifier sends simple prompts to
GPT-6.2 Sol and everything else to GPT-6.2 Astra, billed only at the published OpenAI API rates.
Azure and Bedrock stay ``[verify]`` and are not billed. Quality is simulated, the same way as
``routing.py``: a fixed pass rate per model and difficulty, sampled per request id. It is not a
benchmark score.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from typing import Any

from finops.ai import catalog, routing
from finops.ai.eval_gate import Candidate, gate
from finops.ai.token_cost import cached_prefix_tokens
from finops.datasets import load_ai_requests
from finops.patterns.base import money

ASTRA = catalog.ASTRA
SOL = catalog.SOL
PROVIDER = catalog.OPENAI

# Simulated pass rates (stand-in for an LLM judge). Not taken from a published benchmark.
PASS_RATE = {
    (ASTRA, "simple"): 0.99,
    (ASTRA, "complex"): 0.97,
    (SOL, "simple"): 0.98,
    (SOL, "complex"): 0.90,
}


def model_for_route(req: dict[str, Any]) -> str:
    """Sol when the classifier is sure the prompt is simple; Astra otherwise, including when unsure."""
    tier, _conf = routing.classify(req["prompt"])
    return SOL if tier == routing.SMALL else ASTRA


def passes(req: dict[str, Any], model: str) -> bool:
    h = int(hashlib.sha256(f"{req['request_id']}|{model}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return h < PASS_RATE[(model, req["label"])]


def _cost(reqs: list[dict[str, Any]], model_for, prompt_cache: bool) -> float:
    total = 0.0
    for q in reqs:
        cached = cached_prefix_tokens(q["system_prefix_tokens"]) if prompt_cache else 0
        total += (
            catalog.token_cost(model_for(q), q["prompt_tokens"], q["completion_tokens"], cached, PROVIDER)
            * q["weight"]
        )
    return total


def _quality(reqs: list[dict[str, Any]], model_for) -> float:
    ok = sum(passes(q, model_for(q)) for q in reqs)
    return round(100 * ok / len(reqs), 2)


def simulate(reqs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Compare all-Astra, all-Sol and the routed mix. Costs are monthly USD at published API rates."""
    reqs = list(load_ai_requests() if reqs is None else reqs)
    specs: list[tuple[str, Any, bool]] = [
        ("single-astra", lambda q: ASTRA, False),
        ("single-sol", lambda q: SOL, False),
        ("routed", model_for_route, False),
        ("routed-cache", model_for_route, True),
    ]
    rows = []
    for name, fn, cache in specs:
        rows.append(
            {
                "name": name,
                "monthly_cost": round(_cost(reqs, fn, cache), 2),
                "quality_pct": _quality(reqs, fn),
                "prompt_cache": cache,
            }
        )
    baseline = Candidate(rows[0]["name"], rows[0]["monthly_cost"], rows[0]["quality_pct"])
    decisions = [gate(baseline, Candidate(r["name"], r["monthly_cost"], r["quality_pct"])) for r in rows[1:]]
    mix = Counter(model_for_route(q) for q in reqs)
    single = rows[0]["monthly_cost"]
    routed = rows[2]["monthly_cost"]
    return {
        "provider": PROVIDER,
        "quality": "simulated",
        "stand_in": "two-tier Sol/Astra; the other router models have no published price",
        "router_model_count": catalog.load()["foundry_router"]["model_count"],
        "unpriced_providers": [catalog.AZURE, catalog.BEDROCK],
        "scenarios": rows,
        "decisions": decisions,
        "mix": {ASTRA: mix[ASTRA], SOL: mix[SOL]},
        "savings_vs_single_astra": round(single - routed, 2),
        "savings_pct_vs_single_astra": round(100 * (single - routed) / single, 2) if single else 0.0,
    }


def format_sim(sim: dict[str, Any]) -> list[str]:
    lines = [
        "== routing simulation (published OpenAI API rates; two-tier stand-in for the 44-model router)",
        f"  quality is {sim['quality']}. {sim['stand_in']}.",
        f"  unpriced providers (not billed): {', '.join(sim['unpriced_providers'])}",
    ]
    labels = {
        "single-astra": "single gpt-6.2-astra",
        "single-sol": "single gpt-6.2-sol",
        "routed": "routed simple->sol, else astra",
        "routed-cache": "routed + prompt cache",
    }
    for row, decision in zip(sim["scenarios"], [None, *sim["decisions"]], strict=True):
        extra = ""
        if decision is not None:
            flag = "SHIP " if decision.ship else "BLOCK"
            extra = f"  {flag} save {money(decision.savings)} ({decision.quality_delta:+.2f} pts) {decision.reason}"
        lines.append(
            f"  {labels[row['name']]:<32} {money(row['monthly_cost']):>10}  quality {row['quality_pct']:>6.2f}%{extra}"
        )
    lines.append(
        f"  routed mix: {sim['mix'][SOL]:,} requests on sol, {sim['mix'][ASTRA]:,} on astra "
        f"(of {sim['mix'][SOL] + sim['mix'][ASTRA]:,}); "
        f"save {money(sim['savings_vs_single_astra'])} ({sim['savings_pct_vs_single_astra']}%) vs single astra"
    )
    lines.append(
        "  these totals use the published API card, not the Azure snapshot, so they are not a saving against the reconciled bill"
    )
    return lines
