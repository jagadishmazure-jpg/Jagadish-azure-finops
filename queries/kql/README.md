# `queries/kql/`

Log Analytics queries. Run with `az monitor log-analytics query`.

| File | What it does |
|---|---|
| [`vm-utilization-p95.kql`](vm-utilization-p95.kql) | p95 CPU and memory per VM (p01) |
| [`app-service-cpu.kql`](app-service-cpu.kql) | Plan CPU and instance count (p01, p02) |
| [`container-apps-requests.kql`](container-apps-requests.kql) | Requests and replicas per Container App (p02, p08) |
| [`commitment-coverage.kql`](commitment-coverage.kql) | Commitment coverage from the FOCUS export (p03) |
| [`spot-evictions.kql`](spot-evictions.kql) | Spot evictions per day (p04) |
| [`blob-access-age.kql`](blob-access-age.kql) | Reads by data age (p05) |
| [`hybrid-benefit-coverage.kql`](hybrid-benefit-coverage.kql) | Licence meters still billing (p06) |
| [`serverless-volume.kql`](serverless-volume.kql) | Function executions and duration (p07) |
| [`logic-apps-standard-runs.kql`](logic-apps-standard-runs.kql) | Workflow runs per Logic App (p07, p08) |
| [`cost-anomaly.kql`](cost-anomaly.kql) | Daily cost anomalies per resource (all) |
| [`egress-by-resource.kql`](egress-by-resource.kql) | Egress and cache hit ratio (p10) |
| [`ai-token-cost.kql`](ai-token-cost.kql) | Per-request token cost by tenant, agent, use case |
| [`ai-budget-burn.kql`](ai-budget-burn.kql) | Month-to-date AI burn per tenant vs budget |
