"""Published model rate card, separate from the Azure list-price snapshot.

The snapshot stays the only source for meters that came from the Retail Prices API. This catalog
records rates a vendor published in the sources named in the file, and rows marked ``verify``
where a source named a model or a cloud but did not publish a price. :func:`token_cost` refuses
to bill a verify row, so an unpublished Azure or Bedrock price cannot leak into a total.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from typing import Any

from finops import DATA

CATALOG_PATH = DATA / "pricing" / "model-catalog.json"
PUBLISHED = "published"
VERIFY = "verify"
OPENAI = "openai-api"
AZURE = "azure-foundry"
BEDROCK = "amazon-bedrock"
ASTRA = "gpt-6.2-astra"
SOL = "gpt-6.2-sol"


class UnpublishedPrice(LookupError):
    """Raised when code tries to bill a row whose price was not published."""


@dataclass(frozen=True)
class Rate:
    model: str
    provider: str
    input_per_million: float | None
    cached_input_per_million: float | None
    output_per_million: float | None
    price_status: str
    availability: str
    source: str
    note: str
    cached_discount_wording: str = ""

    @property
    def published(self) -> bool:
        return self.price_status == PUBLISHED


@cache
def load() -> dict[str, Any]:
    doc = json.loads(CATALOG_PATH.read_text())
    _validate(doc)
    return doc


def _validate(doc: dict[str, Any]) -> None:
    router = doc["foundry_router"]
    if router["model_count"] != 44 or router["prices_published"]:
        raise ValueError("foundry router must stay a 44-model set with no published prices")
    ids = {s["id"] for s in doc["sources"]}
    for row in doc["baseten"]["models"]:
        if row["price_status"] != VERIFY:
            raise ValueError(f"baseten {row['id']} has no published price")
    seen: set[tuple[str, str]] = set()
    for raw in doc["rates"]:
        key = (raw["model"], raw["provider"])
        if key in seen:
            raise ValueError(f"duplicate rate {key}")
        seen.add(key)
        if raw["source"] not in ids:
            raise ValueError(f"unknown source {raw['source']}")
        nums = (raw["input_per_million"], raw["cached_input_per_million"], raw["output_per_million"])
        status = raw["price_status"]
        if status == PUBLISHED:
            if any(not isinstance(n, (int, float)) or n < 0 for n in nums):
                raise ValueError(f"{key} published row needs three rates")
            if raw["cached_input_per_million"] > raw["input_per_million"]:
                raise ValueError(f"{key} cached input above input")
        elif status == VERIFY:
            if any(n is not None for n in nums):
                raise ValueError(f"{key} verify row must not carry a number")
        else:
            raise ValueError(f"{key} bad price_status {status}")


def rates() -> list[Rate]:
    return [_rate(raw) for raw in load()["rates"]]


def _rate(raw: dict[str, Any]) -> Rate:
    return Rate(
        model=raw["model"],
        provider=raw["provider"],
        input_per_million=raw["input_per_million"],
        cached_input_per_million=raw["cached_input_per_million"],
        output_per_million=raw["output_per_million"],
        price_status=raw["price_status"],
        availability=raw["availability"],
        source=raw["source"],
        note=raw["note"],
        cached_discount_wording=raw.get("cached_discount_wording", ""),
    )


def get(model: str, provider: str) -> Rate:
    for r in rates():
        if r.model == model and r.provider == provider:
            return r
    raise KeyError(f"no rate for {model} on {provider}")


def token_cost(
    model: str,
    prompt_tokens: float,
    completion_tokens: float,
    cached_tokens: float = 0,
    provider: str = OPENAI,
) -> float:
    """USD for one call at a published per-million rate. Refuses a ``[verify]`` row."""
    r = get(model, provider)
    if not r.published:
        raise UnpublishedPrice(f"{provider} {model} is [verify]; the source published no price")
    pin = r.input_per_million
    pcached = r.cached_input_per_million
    pout = r.output_per_million
    if pin is None or pcached is None or pout is None:
        raise UnpublishedPrice(f"{provider} {model} is [verify]; the source published no price")
    cached = min(max(cached_tokens, 0.0), prompt_tokens)
    return ((prompt_tokens - cached) * pin + cached * pcached + completion_tokens * pout) / 1_000_000


def stated_cached_input(model: str, discount: float, provider: str = OPENAI) -> float:
    """Input rate times ``1 - discount``. This is not the billed cached rate."""
    r = get(model, provider)
    if not r.published or r.input_per_million is None:
        raise UnpublishedPrice(f"{provider} {model} is [verify]; the source published no price")
    return r.input_per_million * (1 - discount)


def source_url(source_id: str) -> str:
    for s in load()["sources"]:
        if s["id"] == source_id:
            return s["url"]
    raise KeyError(source_id)


def _cell(rate: Rate) -> str:
    if not rate.published:
        return "[verify]"
    return f"${rate.input_per_million:.2f} / ${rate.cached_input_per_million:.2f} / ${rate.output_per_million:.2f}"


def format_rate_card() -> list[str]:
    """Plain-text rate card. Prices are input / cached input / output per million tokens."""
    doc = load()
    router = doc["foundry_router"]
    names = ", ".join(m["id"] for m in doc["baseten"]["models"])
    lines = [
        "== model rate card (USD per million tokens: input / cached input / output)",
        f"  foundry router: {router['model_count']} models, automatic selection by default; "
        "per-model prices [verify]",
        f"  baseten on Foundry ({doc['baseten']['status']}): {names}; prices [verify]",
    ]
    for r in rates():
        lines.append(f"  {r.model:<16} {r.provider:<16} {_cell(r):<32} {r.availability}")
    astra = get(ASTRA, OPENAI)
    lines.append(
        f"  astra cached input: announcement says '{astra.cached_discount_wording}'; "
        f"billed rate is ${astra.cached_input_per_million:.2f} "
        f"(a 60% cut off the $8 input rate would be ${stated_cached_input(ASTRA, 0.60):.2f}, which is not billed)"
    )
    return lines


def format_comparison(workload: list[tuple[str, float]]) -> list[str]:
    """Azure vs Bedrock for GPT-6.2. Unpublished cells stay ``[verify]``; the API column is the reference."""
    lines = [
        "== azure vs bedrock (GPT-6.2 token prices; [verify] means the source published no price)",
        f"  {'model':<16} {'azure-foundry':<28} {'amazon-bedrock':<28} openai-api reference",
    ]
    for model in (ASTRA, SOL):
        lines.append(
            f"  {model:<16} {_cell(get(model, AZURE)):<28} {_cell(get(model, BEDROCK)):<28} {_cell(get(model, OPENAI))}"
        )
    lines.append("  same workload, USD / month, still not priced where the source published no rate:")
    lines.append(f"  {'workload':<16} {'azure-foundry':<28} {'amazon-bedrock':<28} openai-api reference")
    for name, cost in workload:
        lines.append(f"  {name:<16} {'[verify]':<28} {'[verify]':<28} ${cost:,.2f}")
    lines.append("  bedrock: generally available. azure: availability not stated in the sources.")
    return lines


def format_sources() -> list[str]:
    lines = ["  sources:"]
    for s in load()["sources"]:
        lines.append(f"    {s['title']}: {s['url']}")
    return lines
