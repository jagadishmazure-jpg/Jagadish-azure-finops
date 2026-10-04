# `infra/terraform/envs/`

Per-environment settings.

| File | What it does |
|---|---|
| [`dev.tfvars`](dev.tfvars) | Dev: $10 budget, Audit effect |
| [`prod.tfvars`](prod.tfvars) | Prod: $25 budget, Deny effect |
| [`dev.backend.hcl`](dev.backend.hcl) | Dev state key |
| [`prod.backend.hcl`](prod.backend.hcl) | Prod state key |
