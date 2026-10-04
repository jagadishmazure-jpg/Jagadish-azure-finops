"""The ten Azure cost-optimization patterns. Each module exposes ``analyze() -> PatternResult``."""

from importlib import import_module

MODULES = [
    "p01_rightsize",
    "p02_autoscale",
    "p03_commitments",
    "p04_spot",
    "p05_storage_tiering",
    "p06_hybrid_benefit",
    "p07_serverless",
    "p08_idle_cleanup",
    "p09_tagging_chargeback",
    "p10_cache_egress",
]


def all_results():
    return [import_module(f"finops.patterns.{m}").analyze() for m in MODULES]
