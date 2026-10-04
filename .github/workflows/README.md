# `.github/workflows/`

Workflows.

| File | What it does |
|---|---|
| [`ci.yml`](ci.yml) | Lint, tests, data and doc drift, scans, bicep build |
| [`infra.yml`](infra.yml) | Terraform fmt/validate/test, tflint, checkov, optional plan |
| [`deploy.yml`](deploy.yml) | Gated deploy: OIDC, dev then prod with approval, Terraform or Bicep |
| [`teardown.yml`](teardown.yml) | Gated, confirmed teardown of one environment |
