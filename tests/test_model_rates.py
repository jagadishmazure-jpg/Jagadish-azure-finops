"""Published GPT-6.2 rates, the routing simulation, and per-agent cost and value.

Azure and Bedrock rows are [verify]: those sources did not publish a token price, and nothing
here is allowed to bill a made-up one. Dollar figures are the published OpenAI API card applied
to the synthetic request log.
"""

from pathlib import Path

import pytest

from finops.ai import catalog, route_sim, routing
from finops.ai.agent_value import assisted, build
from finops.ai.report import analyze, report
from finops.ai.roi import roi
from finops.ai.token_cost import attribute
from finops.datasets import load_ai_requests, load_json

ROOT = Path(__file__).resolve().parents[1]
ASTRA, SOL = "gpt-6.2-astra", "gpt-6.2-sol"


def _req(**over):
    base = {
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
    base.update(over)
    return base


@pytest.fixture(scope="module")
def sim():
    return route_sim.simulate()


@pytest.fixture(scope="module")
def agents():
    return build()


@pytest.fixture(scope="module")
def ai():
    return analyze()


def test_published_astra_and_sol_rates():
    astra = catalog.get(ASTRA, catalog.OPENAI)
    sol = catalog.get(SOL, catalog.OPENAI)
    assert (astra.input_per_million, astra.cached_input_per_million, astra.output_per_million) == (
        8.0,
        0.4,
        40.0,
    )
    assert (sol.input_per_million, sol.cached_input_per_million, sol.output_per_million) == (2.0, 0.1, 10.0)
    assert astra.published and sol.published


def test_sixty_percent_wording_is_not_the_billed_cached_rate():
    astra = catalog.get(ASTRA, catalog.OPENAI)
    assert astra.cached_discount_wording == "60% discount on cached input"
    stated = catalog.stated_cached_input(ASTRA, 0.60)
    assert stated == pytest.approx(3.2)
    assert astra.cached_input_per_million == pytest.approx(0.4)
    assert stated != pytest.approx(astra.cached_input_per_million)


def test_token_cost_uses_per_million_rates():
    assert catalog.token_cost(ASTRA, 1_000_000, 500_000) == pytest.approx(28)
    assert catalog.token_cost(ASTRA, 1_000_000, 0, cached_tokens=1_000_000) == pytest.approx(0.4)
    assert catalog.token_cost(SOL, 2_000_000, 1_000_000, cached_tokens=500_000) == pytest.approx(13.05)


def test_prompt_cache_bills_the_published_cached_rate():
    bare = route_sim._cost([_req()], lambda q: ASTRA, False)
    cached = route_sim._cost([_req()], lambda q: ASTRA, True)
    assert bare - cached == pytest.approx(1280 * (8.0 - 0.4) / 1_000_000)


def test_verify_rows_have_no_numbers_and_cannot_be_billed():
    for provider in (catalog.AZURE, catalog.BEDROCK):
        for model in (ASTRA, SOL):
            rate = catalog.get(model, provider)
            assert rate.price_status == "verify"
            assert rate.input_per_million is None
            assert rate.cached_input_per_million is None
            assert rate.output_per_million is None
            with pytest.raises(catalog.UnpublishedPrice):
                catalog.token_cost(model, 1000, 100, provider=provider)


def test_validator_rejects_a_number_on_a_verify_row():
    doc = catalog.load()
    broken = {
        **doc,
        "rates": [{**doc["rates"][0], "input_per_million": 8.0}, *doc["rates"][1:]],
    }
    with pytest.raises(ValueError, match="verify row"):
        catalog._validate(broken)


def test_router_spans_44_models_without_prices():
    router = catalog.load()["foundry_router"]
    assert router["model_count"] == 44
    assert router["automatic_selection_by_default"] is True
    assert router["prices_published"] is False
    assert "AI Gateway" in router["surfaces"]


def test_baseten_models_are_named_and_unpriced():
    models = catalog.load()["baseten"]["models"]
    assert [m["id"] for m in models] == ["Kimi-K3", "GLM 5.3", "GLM-5.3-Flash", "DeepSeek V4.1-Flash-1017"]
    assert all(m["price_status"] == "verify" for m in models)
    assert catalog.load()["baseten"]["status"] == "public preview"


def test_classifier_maps_onto_sol_and_astra():
    assert route_sim.model_for_route({"prompt": "where is shipment 1001"}) == SOL
    assert (
        route_sim.model_for_route({"prompt": "review the proof of delivery notes and draft a reply"}) == ASTRA
    )
    unsure = "can you tell me whether the delivery for order 1001 still arrives today"
    assert route_sim.model_for_route({"prompt": unsure}) == ASTRA


def test_mix_matches_the_existing_classifier():
    reqs = load_ai_requests()
    sim = route_sim.simulate(reqs)
    conf = routing.confusion(reqs)
    assert sim["mix"][SOL] == conf["simple->small"] + conf["complex->small"] == 2988
    assert sim["mix"][ASTRA] == conf["simple->large"] + conf["complex->large"] == 3012


def test_routed_saves_against_single_astra_and_ships(sim):
    by = {r["name"]: r for r in sim["scenarios"]}
    assert by["single-astra"]["monthly_cost"] == 1982.13
    assert by["single-astra"]["quality_pct"] == 98.23
    assert by["routed"]["monthly_cost"] == 1575.97
    assert by["routed"]["quality_pct"] == 97.85
    assert sim["savings_vs_single_astra"] == 406.16
    assert sim["savings_pct_vs_single_astra"] == 20.49
    decision = {d.name: d for d in sim["decisions"]}["routed"]
    assert decision.ship and decision.savings == 406.16 and decision.quality_delta == -0.38


def test_all_sol_is_blocked_on_quality(sim):
    decision = {d.name: d for d in sim["decisions"]}["single-sol"]
    assert not decision.ship
    assert decision.savings == pytest.approx(1486.60)
    assert decision.quality_delta == pytest.approx(-3.70)


def test_prompt_cache_keeps_quality_and_saves_more(sim):
    by = {r["name"]: r for r in sim["scenarios"]}
    decision = {d.name: d for d in sim["decisions"]}["routed-cache"]
    assert by["routed-cache"]["monthly_cost"] == 1210.29
    assert by["routed-cache"]["quality_pct"] == by["routed"]["quality_pct"]
    assert decision.ship and decision.savings == 771.84 and decision.quality_delta == -0.38


def test_simulation_does_not_price_azure_or_bedrock(sim):
    assert sim["provider"] == catalog.OPENAI
    assert sim["unpriced_providers"] == [catalog.AZURE, catalog.BEDROCK]
    assert sim["router_model_count"] == 44
    assert sim["quality"] == "simulated"
    text = "\n".join(catalog.format_comparison([(r["name"], r["monthly_cost"]) for r in sim["scenarios"]]))
    assert text.count("[verify]") >= 8
    assert "$8.00 / $0.40 / $40.00" in text and "$2.00 / $0.10 / $10.00" in text


def test_agent_costs_match_attribution_and_the_route(agents, sim):
    assert sum(r["token_cost"] for r in agents) == pytest.approx(attribute(load_ai_requests())["total"])
    routed = next(s["monthly_cost"] for s in sim["scenarios"] if s["name"] == "routed")
    cached = next(s["monthly_cost"] for s in sim["scenarios"] if s["name"] == "routed-cache")
    assert sum(r["routed_token_cost"] for r in agents) == pytest.approx(routed, abs=0.02)
    assert sum(r["routed_cached_token_cost"] for r in agents) == pytest.approx(cached, abs=0.02)


def test_assisted_value_matches_the_use_case_assumptions(agents):
    cases = {u["use_case"]: u for u in load_json("ai/use-cases.json")}
    for row in agents:
        hours, value = assisted(cases[row["use_case"]], row["tasks"])
        assert row["assisted_hours"] == pytest.approx(hours)
        assert row["assisted_value"] == pytest.approx(value)
        loaded = roi(cases[row["use_case"]], row["tasks"], row["token_cost"])
        assert row["verdict"] == loaded["verdict"]
        assert loaded["value"] == round(value, 2)
        assert row["satisfaction"] is None


def test_dispatch_stays_a_rework_when_repriced(agents):
    row = next(r for r in agents if r["agent"] == "dispatch-summarizer")
    assert row["verdict"] == "rework or retire"
    assert row["routed_verdict"] == "rework or retire"
    assert row["routed_token_cost"] > row["token_cost"]


def test_report_prints_the_rate_card_the_simulation_and_the_agents(ai):
    text = report(ai)
    assert "44 models" in text and "[verify]" in text
    assert "save $406.16" in text and "BLOCK" in text and "SHIP" in text
    assert "satisfaction: not logged" in text
    assert "not a saving against the reconciled bill" in text
    for source in catalog.load()["sources"]:
        assert source["url"] in text


def test_readme_and_ai_finops_link_every_source():
    urls = [s["url"] for s in catalog.load()["sources"]]
    for rel in ("README.md", "docs/ai-finops.md"):
        text = (ROOT / rel).read_text()
        assert "## AI model rates" in text or "## 8. Published rate card" in text
        for url in urls:
            assert url in text, f"{url} missing from {rel}"
