"""Model routing with a cheap "System 1" classifier in front of the models.

A fast, deterministic classifier (no model call) decides whether a request is simple enough for
the small model. Anything it is unsure about goes to the large model, so mistakes cost money,
not quality. The classifier is rules over the prompt; in production it could be a tiny trained
model, and it must be evaluated the same way.

Quality is SIMULATED offline: each (model, difficulty) pair has a pass rate standing in for a
golden-set judge, sampled deterministically per request id. The numbers show how the gate works;
real pass rates come from your own eval set.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

SMALL, LARGE = "gpt-4o-mini", "gpt-4o"
COMPLEX_CUES = {"explain", "propose", "summarize", "review", "compare", "recommend", "draft", "dispute", "claims", "mismatch"}
SIMPLE_CUES = {"where", "eta", "track", "status", "late"}
MAX_SIMPLE_WORDS = 9

# SIMULATED pass rates (stand-in for an LLM judge over a golden set)
PASS_RATE = {(LARGE, "simple"): 0.98, (LARGE, "complex"): 0.95, (SMALL, "simple"): 0.97, (SMALL, "complex"): 0.70}


def classify(prompt: str) -> tuple[str, float]:
    """Return (route, confidence). Unsure -> large model."""
    words = re.findall(r"[a-z]+", prompt.lower())
    ws = set(words)
    if ws & COMPLEX_CUES:
        return LARGE, 0.95
    if ws & SIMPLE_CUES and len(words) <= MAX_SIMPLE_WORDS:
        return SMALL, 0.9
    return LARGE, 0.5  # fail safe


def route(req: dict[str, Any]) -> str:
    return classify(req["prompt"])[0]


def passes(req: dict[str, Any], model: str) -> bool:
    h = int(hashlib.sha256(f"{req['request_id']}|{model}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return h < PASS_RATE[(model, req["label"])]


def quality(requests: list[dict[str, Any]], model_for) -> float:
    ok = sum(passes(q, model_for(q)) for q in requests)
    return round(100 * ok / len(requests), 2)


def confusion(requests: list[dict[str, Any]]) -> dict[str, int]:
    out = {"simple->small": 0, "simple->large": 0, "complex->small": 0, "complex->large": 0}
    for q in requests:
        out[f"{q['label']}->{'small' if route(q) == SMALL else 'large'}"] += 1
    return out
