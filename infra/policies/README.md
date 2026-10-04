# `infra/policies/`

Policy rules as JSON, loaded by Terraform (`jsondecode(file())`) and Bicep (`loadJsonContent`).

| File | What it does |
|---|---|
| [`require-tags.json`](require-tags.json) | Require cost-center, owner, env and app tags |
| [`allowed-vm-skus.json`](allowed-vm-skus.json) | Restrict VM sizes to an allowed list |
| [`deny-untagged-public-ip.json`](deny-untagged-public-ip.json) | Deny public IPs without owner and cost-center tags |
