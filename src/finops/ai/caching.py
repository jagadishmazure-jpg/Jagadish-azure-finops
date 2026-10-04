"""Response caching for repeated questions: exact cache, then a semantic cache.

Rules that keep a cache from serving wrong or leaked answers:
  * the key always includes the tenant (no cross-tenant hits) and the agent;
  * entries expire (TTL in days; shipment status goes stale);
  * semantic hits require the same entity numbers, so "shipment 1001" never answers 1002;
  * only intents marked cacheable are cached (status lookups, not free-form analysis).

The semantic similarity here is a deterministic stand-in (synonym-normalized bag of words with
cosine similarity). In Azure the same logic runs on embeddings in a vector store such as Azure
Managed Redis or AI Search.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

SYNONYMS = {
    "where": "status", "track": "status", "show": "status", "status": "status",
    "eta": "eta", "late": "eta", "when": "eta",
    "shipment": "shipment", "parcel": "shipment", "order": "shipment", "load": "shipment", "delivery": "shipment",
}
STOP = {"is", "the", "for", "of", "what", "a"}
CACHEABLE_AGENTS = {"eta-assistant"}
THRESHOLD = 0.85


def normalize(prompt: str) -> str:
    return " ".join(prompt.lower().split())


def vector(prompt: str) -> Counter:
    words = re.findall(r"[a-z]+", prompt.lower())
    return Counter(SYNONYMS.get(w, w) for w in words if w not in STOP)


def numbers(prompt: str) -> tuple[str, ...]:
    return tuple(re.findall(r"\d+", prompt))


def cosine(a: Counter, b: Counter) -> float:
    dot = sum(a[k] * b[k] for k in a)
    na, nb = math.sqrt(sum(v * v for v in a.values())), math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


class ResponseCache:
    def __init__(self, ttl_days: int = 1, semantic: bool = True, threshold: float = THRESHOLD):
        self.ttl = ttl_days
        self.semantic = semantic
        self.threshold = threshold
        self.last_wrong = False
        self.exact: dict[tuple, int] = {}
        self.entries: dict[tuple, list[tuple[Counter, int]]] = {}

    def lookup(self, req: dict[str, Any]) -> str:
        """Return 'exact', 'semantic' or 'miss', and store the request on a miss. After a semantic
        hit, ``last_wrong`` says whether the cached answer was for a different intent."""
        self.last_wrong = False
        if req["agent"] not in CACHEABLE_AGENTS or req["label"] != "simple":
            return "miss"
        day = req["day"]
        key = (req["tenant"], req["agent"], normalize(req["prompt"]))
        if key in self.exact and day - self.exact[key] < self.ttl:
            return "exact"
        scope = (req["tenant"], req["agent"], numbers(req["prompt"]))
        vec = vector(req["prompt"])
        if self.semantic:
            for v, d in self.entries.get(scope, []):
                if day - d < self.ttl and cosine(vec, v) >= self.threshold:
                    self.last_wrong = set(v) != set(vec)
                    return "semantic"
        self.exact[key] = day
        self.entries.setdefault(scope, []).append((vec, day))
        return "miss"


def simulate(requests: list[dict[str, Any]], ttl_days: int = 1, semantic: bool = True, threshold: float = THRESHOLD) -> dict[str, Any]:
    cache = ResponseCache(ttl_days, semantic, threshold)
    out = Counter()
    hits, wrong = set(), set()
    for q in sorted(requests, key=lambda r: (r["day"], r["request_id"])):
        kind = cache.lookup(q)
        out[kind] += 1
        if kind != "miss":
            hits.add(q["request_id"])
        if cache.last_wrong:
            wrong.add(q["request_id"])
    return {"exact": out["exact"], "semantic": out["semantic"], "miss": out["miss"], "hit_ids": hits, "wrong_ids": wrong,
            "hit_rate": round(100 * (out["exact"] + out["semantic"]) / len(requests), 2)}
