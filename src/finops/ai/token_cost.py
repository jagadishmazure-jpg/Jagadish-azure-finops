"""Per-request token cost attribution.

The FOCUS export only shows one Azure OpenAI line per meter per day: it cannot tell you which
tenant, agent or use case spent the money. Attribution joins the request log (every call logs
tenant, agent, use case, model and token counts; see ``queries/kql/ai-token-cost.kql``) with the
list-price snapshot, then reconciles the total back to the bill.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from finops.pricing import PriceBook, default_book

MODELS = ("gpt-4o", "gpt-4o-mini")
PROMPT_CACHE_MIN_TOKENS = 1024  # provider prompt caching starts at 1,024 identical prefix tokens
PROMPT_CACHE_BLOCK = 128  # and grows in 128-token blocks


def cached_prefix_tokens(prefix: int) -> int:
    if prefix < PROMPT_CACHE_MIN_TOKENS:
        return 0
    return prefix // PROMPT_CACHE_BLOCK * PROMPT_CACHE_BLOCK


def request_cost(
    req: dict[str, Any], model: str | None = None, prompt_cache: bool = False, book: PriceBook | None = None
) -> float:
    """List cost of one call (unweighted). ``prompt_cache`` bills the shared prefix at the cached
    input rate where the snapshot has one (gpt-4o); other models fall back to the input rate."""
    book = book or default_book()
    model = model or req["model"]
    pin = book.price(f"aoai.{model}.input_1k")
    pcached = book.price(f"aoai.{model}.cached_input_1k") if f"aoai.{model}.cached_input_1k" in book else pin
    pout = book.price(f"aoai.{model}.output_1k")
    cached = cached_prefix_tokens(req["system_prefix_tokens"]) if prompt_cache else 0
    return ((req["prompt_tokens"] - cached) * pin + cached * pcached + req["completion_tokens"] * pout) / 1000


def attribute(requests: list[dict[str, Any]], model_for=None, prompt_cache: bool = False) -> dict[str, Any]:
    """Weighted monthly cost by tenant, agent and use case. ``model_for(req)`` overrides the model."""
    by: dict[str, dict[str, float]] = {
        "tenant": defaultdict(float),
        "agent": defaultdict(float),
        "use_case": defaultdict(float),
    }
    costs = []
    total = 0.0
    for q in requests:
        c = request_cost(q, model_for(q) if model_for else None, prompt_cache)
        costs.append(c)
        w = c * q["weight"]
        total += w
        for k in by:
            by[k][q[k]] += w
    costs.sort()
    return {
        "total": total,
        "by_tenant": dict(sorted(by["tenant"].items())),
        "by_agent": dict(sorted(by["agent"].items())),
        "by_use_case": dict(sorted(by["use_case"].items())),
        "per_request_p50": costs[len(costs) // 2],
        "per_request_p95": costs[int(len(costs) * 0.95)],
        "requests": sum(q["weight"] for q in requests),
    }


def reconcile(attributed_total: float, billed_total: float, tolerance: float = 0.01) -> dict[str, Any]:
    gap = round(attributed_total - billed_total, 2) + 0.0  # + 0.0 turns -0.0 into 0.0
    return {
        "attributed": round(attributed_total, 2),
        "billed": round(billed_total, 2),
        "gap": round(gap, 2),
        "ok": abs(gap) <= tolerance * max(billed_total, 1e-9),
    }
