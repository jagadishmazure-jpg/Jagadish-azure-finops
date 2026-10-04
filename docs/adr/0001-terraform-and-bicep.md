# ADR 0001: Terraform and Bicep for the same guardrails

- **Status:** Accepted

## Context

FinOps guardrails (policies, budgets, alerts, lifecycle rules) belong in IaC so they cannot drift.
Some teams run Terraform across clouds; others are Azure-only and prefer Bicep with no state file.

## Decision

Ship both, from one source of truth for the policy rules: `infra/policies/*.json` is loaded by
Terraform (`file()`/`jsondecode`) and by Bicep (`loadJsonContent`). The deploy workflow takes a
`deploy_tool` input.

## Consequences

- A change to a policy is made once; a change to other resources is made twice.
- One environment must be owned by one tool.
- CI checks both: `bicep build` with zero warnings, and Terraform fmt, validate, test, tflint and
  checkov.
