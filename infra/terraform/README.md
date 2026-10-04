# `infra/terraform/`

Terraform stack: policy definitions and assignments, action group, budget, storage with lifecycle, opt-in autoscale.

| File | What it does |
|---|---|
| [`versions.tf`](versions.tf) | Terraform and provider versions |
| [`providers.tf`](providers.tf) | azurerm provider (Entra ID for storage) |
| [`backend.tf`](backend.tf) | Partial azurerm backend |
| [`variables.tf`](variables.tf) | Inputs with validation |
| [`locals.tf`](locals.tf) | Names, tags, budget notifications, policy files |
| [`main.tf`](main.tf) | All resources |
| [`outputs.tf`](outputs.tf) | Outputs used by the deploy script |
| [`.tflint.hcl`](.tflint.hcl) | tflint configuration |
| [`envs/`](envs/) | Per-environment tfvars and backend config |
| [`tests/`](tests/) | Offline `terraform test` with a mocked provider |
