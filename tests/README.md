# `tests/`

pytest suite, offline. Run `pytest -q`.

| File | What it does |
|---|---|
| [`conftest.py`](conftest.py) | Shared fixtures |
| [`test_pricing.py`](test_pricing.py) | Price book and snapshot |
| [`test_data.py`](test_data.py) | Synthetic data and FOCUS |
| [`test_p01_rightsize.py`](test_p01_rightsize.py) | Pattern 1 |
| [`test_p02_autoscale.py`](test_p02_autoscale.py) | Pattern 2 |
| [`test_p03_commitments.py`](test_p03_commitments.py) | Pattern 3 |
| [`test_p04_spot.py`](test_p04_spot.py) | Pattern 4 |
| [`test_p05_storage.py`](test_p05_storage.py) | Pattern 5 |
| [`test_p06_hybrid_benefit.py`](test_p06_hybrid_benefit.py) | Pattern 6 |
| [`test_p07_serverless.py`](test_p07_serverless.py) | Pattern 7 |
| [`test_p08_idle_cleanup.py`](test_p08_idle_cleanup.py) | Pattern 8 |
| [`test_p09_tagging.py`](test_p09_tagging.py) | Pattern 9 |
| [`test_p10_cache_egress.py`](test_p10_cache_egress.py) | Pattern 10 |
| [`test_ai_finops.py`](test_ai_finops.py) | AI FinOps |
| [`test_agent.py`](test_agent.py) | Analyzer, plans, approvals |
| [`test_mcp_and_cli.py`](test_mcp_and_cli.py) | MCP server, case study, CLI |
| [`test_iac.py`](test_iac.py) | Policy JSON, Terraform and Bicep structure; workflow supply-chain guard (pinned actions, permissions, gitleaks, CodeQL, Dependabot) |
| [`test_repo_hygiene.py`](test_repo_hygiene.py) | READMEs, no dates, no secrets, doc sections, doc drift |
| [`test_render_docs.py`](test_render_docs.py) | Doc renderer: output blocks and code excerpts |
