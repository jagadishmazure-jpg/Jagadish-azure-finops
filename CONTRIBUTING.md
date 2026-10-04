# Contributing

Thanks for taking a look. Issues and pull requests are welcome.

## Setup

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

## Rules for a change

1. **Numbers come from code.** If you change a pattern, prices or data, run
   `python scripts/render_docs.py` so every doc block is regenerated, and commit the result. CI runs
   `--check`.
2. **Data is generated.** Edit `src/finops/synth.py`, then `python scripts/generate_data.py`. Never
   hand-edit files under `data/` (except READMEs).
3. **Label assumptions.** A finding that depends on an assumption sets `estimate=True`.
4. **Keep the safety model.** No tool or code path may apply changes to Azure; no approve tool on
   the MCP server.
5. **No real identifiers.** No subscription or tenant IDs, real company names or personal emails.
6. **No dates in docs.** Docs describe behaviour, not timelines.
7. **IaC changes in both tools,** or explain the difference in the folder README.
8. **Style:** `ruff check . && ruff format .`

## Adding a pattern

Create `src/finops/patterns/pNN_name.py` with `analyze() -> PatternResult`, add it to `MODULES`,
add `tests/test_pNN_*.py`, add `docs/patterns/NN-name.md` with the 13 standard sections (the
hygiene test checks them), and a query in `queries/`.
