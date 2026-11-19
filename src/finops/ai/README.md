# `src/finops/ai/`

AI FinOps.

| File | What it does |
|---|---|
| [`__init__.py`](__init__.py) | Package marker |
| [`token_cost.py`](token_cost.py) | Per-request cost, attribution, reconciliation |
| [`catalog.py`](catalog.py) | Published model rate card; refuses to bill a `[verify]` row |
| [`route_sim.py`](route_sim.py) | Single-model vs routed savings on published GPT-6.2 rates |
| [`agent_value.py`](agent_value.py) | Per-agent cost, assisted value, success rate and verdict |
| [`routing.py`](routing.py) | System-1 classifier and simulated quality |
| [`caching.py`](caching.py) | Exact and semantic response cache |
| [`budgets.py`](budgets.py) | Per-agent and per-tenant budget enforcement |
| [`ptu.py`](ptu.py) | PTU vs pay-as-you-go break-even |
| [`roi.py`](roi.py) | ROI per use case |
| [`eval_gate.py`](eval_gate.py) | Ship or block on quality |
| [`report.py`](report.py) | The `finops ai` report |
