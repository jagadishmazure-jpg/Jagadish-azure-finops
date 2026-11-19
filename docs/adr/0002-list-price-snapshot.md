# ADR 0002: Price from a checked-in list-price snapshot

- **Status:** Accepted

## Context

Savings math needs prices. Calling the Retail Prices API in tests makes them slow, flaky and
non-reproducible, and hard-coding prices in code hides where they came from.

## Decision

Capture the meters the patterns use into `data/pricing/retail-prices-snapshot.json` with
`scripts/refresh_prices.py`, label the file as a **list-price snapshot**, and read every Azure
list price through `PriceBook`. Refreshing is a deliberate commit that also regenerates the docs.

Published token rates that did not come from that API (the GPT-6.2 API card) live in
`data/pricing/model-catalog.json`. A row whose source did not publish a price is marked
`verify` and `token_cost` refuses to bill it. Azure and Bedrock prices for those new models
are in that state. They are not copied into the snapshot and they are not filled in from the
API card.

## Consequences

- Tests and docs are reproducible offline.
- Prices are list prices for one region; negotiated rates, credits and most free grants are not
  reflected. Every doc says so.
- A refresh can change headline numbers; `render_docs.py --check` makes that visible in review.
