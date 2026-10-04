# `scripts/`

Maintenance scripts.

| File | What it does |
|---|---|
| [`generate_data.py`](generate_data.py) | Regenerate synthetic data; `--check` verifies it |
| [`refresh_prices.py`](refresh_prices.py) | Re-capture the list-price snapshot (network); `--check` compares with the live API |
| [`render_docs.py`](render_docs.py) | Refresh command output and code excerpts in docs; `--check` for CI |
| [`overlap_check.py`](overlap_check.py) | Originality check against reference texts (expects 0 overlaps) |
