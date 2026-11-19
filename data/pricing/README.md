# `data/pricing/`

Prices. `retail-prices-snapshot.json` is a **list-price snapshot** of the public Azure Retail Prices API (East US 2), captured by `scripts/refresh_prices.py`. `model-catalog.json` is a separate rate card: published token rates, and `[verify]` rows where a source named a model but did not publish a price. The two files are not mixed.

| File | What it does |
|---|---|
| [`retail-prices-snapshot.json`](retail-prices-snapshot.json) | 75 meters with tiers, reservation and savings plan prices |
| [`model-catalog.json`](model-catalog.json) | GPT-6.2 Astra and Sol rates, the 44-model Foundry router, and Baseten open models; Azure and Bedrock prices for the new models are `[verify]` |
