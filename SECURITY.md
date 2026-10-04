# Security policy

## Scope

This repository contains offline code, synthetic data and infrastructure templates. It holds no
credentials, subscription IDs, tenant IDs or customer data, and its tests enforce that.

## Reporting a vulnerability

Please open a private security advisory on GitHub (Security tab, "Report a vulnerability") rather
than a public issue. Include the file, the problem and how to reproduce it. I aim to reply within
a few working days.

## Design choices that matter for security

- **No secrets anywhere.** GitHub Actions log in to Azure with OIDC federated credentials; there is
  no client secret to leak. Terraform state uses Entra ID auth with shared keys disabled.
- **Read-only by default.** Connecting to a real subscription needs only Reader, Cost Management
  Reader, Log Analytics Reader and Storage Blob Data Reader.
- **No autonomous changes.** The FinOps agent drafts plans; approvals are digest-bound, expire
  after 72 hours, cannot come from the requester, and need two people for irreversible steps. The
  executor is dry-run only, and the MCP server has no approve tool.
- **Tamper-evident audit.** Plan, approval, refusal and dry-run events go to a hash-chained log.
- **Tenant isolation in AI caching.** Cache keys include tenant and agent; semantic hits must
  match entity numbers.
- **Deploy gated off** until `DEPLOY_ENABLED` is set; prod needs environment reviewers.
- **Scanned IaC.** checkov runs on Terraform in CI; every skipped check is justified in
  `.checkov.yaml`.

## Supported versions

Only the `main` branch is maintained.
