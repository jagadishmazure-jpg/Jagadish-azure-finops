# Security policy

## Scope

This repository contains offline code, synthetic data and infrastructure templates. It holds no
credentials, subscription IDs, tenant IDs or customer data, and its tests enforce that.

## Reporting a vulnerability

Please do not open a public issue with the details.

1. Open a private security advisory on GitHub (Security tab, "Report a vulnerability"). Include the
   file, the problem and how to reproduce it.
2. If that button is not shown, open an issue titled `Security contact request` with no technical
   details, and I will reply with a private channel.

I aim to reply within a few working days. This is a personal portfolio maintained by one person, so
there is no formal SLA or bug bounty.

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
- **Supply chain:** every third-party GitHub Action is pinned to a full commit SHA with its version in a comment, and every workflow starts from read-only `permissions`. Dependabot proposes weekly, grouped updates ([`.github/dependabot.yml`](.github/dependabot.yml)); CodeQL scans the Python code and the workflow files ([`codeql.yml`](.github/workflows/codeql.yml)); gitleaks scans the full git history in CI. A test (`test_workflows_are_hardened`) fails if an action is left unpinned or a workflow loses its `permissions` block.
- **SBOM:** the `sbom` job in [`ci.yml`](.github/workflows/ci.yml) builds an SPDX JSON software bill of materials from the lockfiles and manifests on every run and keeps it as the `sbom.spdx.json` build artifact. The repository ships no container image, so there is no image scan or provenance step.
- **GitHub settings:** secret scanning with push protection, Dependabot alerts and security updates, private vulnerability reporting, and a ruleset on `main` that blocks force-pushes and branch deletion and requires the CI checks before a pull request can merge. The maintainer (repository admin) can still push directly to `main`, so for direct pushes the checks run after the push rather than before it.

## Supported versions

Only the `main` branch is maintained.
