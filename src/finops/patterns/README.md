# `src/finops/patterns/`

One module per pattern. Each exposes `analyze() -> PatternResult`.

| File | What it does |
|---|---|
| [`__init__.py`](__init__.py) | Module list |
| [`base.py`](base.py) | Finding, PatternResult, report, percentile |
| [`p01_rightsize.py`](p01_rightsize.py) | Rightsize compute |
| [`p02_autoscale.py`](p02_autoscale.py) | Autoscale |
| [`p03_commitments.py`](p03_commitments.py) | Reservations and savings plans |
| [`p04_spot.py`](p04_spot.py) | Spot with eviction simulation and checkpoints |
| [`p05_storage_tiering.py`](p05_storage_tiering.py) | Storage lifecycle tiering |
| [`p06_hybrid_benefit.py`](p06_hybrid_benefit.py) | Azure Hybrid Benefit |
| [`p07_serverless.py`](p07_serverless.py) | Serverless first |
| [`p08_idle_cleanup.py`](p08_idle_cleanup.py) | Idle and orphaned resources |
| [`p09_tagging_chargeback.py`](p09_tagging_chargeback.py) | Tagging, showback, chargeback, budgets |
| [`p10_cache_egress.py`](p10_cache_egress.py) | Cache and egress |
