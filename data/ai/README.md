# `data/ai/`

Inputs for the AI FinOps layer.

| File | What it does |
|---|---|
| [`requests.jsonl`](requests.jsonl) | 6,000 sampled model calls (weight 10 each): tenant, agent, use case, model, tokens, difficulty label |
| [`budgets.json`](budgets.json) | Monthly budgets per tenant and agent, alert/degrade/block levels, critical agents |
| [`use-cases.json`](use-cases.json) | Value assumptions per use case: adoption, minutes saved, loaded rate, build and platform cost |
