# ADR 0002: Price from a checked-in list-price snapshot

- **Status:** Accepted

## Context

Savings math needs prices. Calling the Retail Prices API in tests makes them slow, flaky and
non-reproducible, and hard-coding prices in code hides where they came from.

## Decision

Capture the meters the patterns use into `data/pricing/retail-prices-snapshot.json` with
`scripts/refresh_prices.py`, label the file as a **list-price snapshot**, and read every price
through `PriceBook`. Refreshing is a deliberate commit that also regenerates the docs.

## Consequences

- Tests and docs are reproducible offline.
- Prices are list prices for one region; negotiated rates, credits and most free grants are not
  reflected. Every doc says so.
- A refresh can change headline numbers; `render_docs.py --check` makes that visible in review.
