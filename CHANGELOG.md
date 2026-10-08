# Changelog

All notable changes are recorded here. The format follows Keep a Changelog.

## Unreleased

### Added

- Threat model (`docs/security/threat-model.md`): STRIDE, OWASP Top 10 for LLM Applications and MITRE ATLAS mapped to this repository's components, each row with its control, test evidence and built / planned status.
- SBOM job in CI: an SPDX JSON software bill of materials of the source tree on every run (artifact `sbom.spdx.json`).
- Supply-chain hardening: every GitHub Action pinned to a commit SHA with a version comment, top-level `permissions` on every workflow, a gitleaks job in CI, a CodeQL workflow, `.github/dependabot.yml` and a guard test (`test_workflows_are_hardened`).
- GitHub settings: Dependabot alerts and security updates, private vulnerability reporting and a `main` ruleset (no force-push or deletion; CI required on pull requests).
- Ten Azure cost optimization patterns with tests and full docs: rightsize, autoscale,
  commitments, Spot, storage tiering, Hybrid Benefit, serverless, idle cleanup, tagging and
  chargeback, cache and egress.
- AI FinOps layer: per-request token attribution with reconciliation, System-1 model routing,
  prompt and semantic caching, budget guardrails, PTU break-even, ROI per use case, eval gate.
- FinOps agent: analyzer, digest-bound change plans, approval rules, hash-chained audit log,
  dry-run executor, MCP server with seven tools, `finops mcp-demo`.
- Anonymized case study: idle Logic Apps Standard WS1 plan and a warm Container App.
- Deterministic synthetic data for a fictional company and a FOCUS-format cost export.
- Azure Retail Prices list-price snapshot and refresh script.
- Resource Graph and Log Analytics queries for every signal.
- Terraform and Bicep guardrails: policy definitions, budget, action group, lifecycle policy,
  autoscale example.
- GitHub Actions: ci, infra, gated deploy (OIDC, dev to prod approval, Terraform or Bicep),
  teardown.
- Docs: implementation guide, FinOps maturity, best practices, architecture, deployment,
  interview guide, six ADRs.
