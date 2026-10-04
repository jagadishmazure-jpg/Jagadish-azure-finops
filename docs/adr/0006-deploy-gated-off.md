# ADR 0006: Deploy workflows exist but are gated off

- **Status:** Accepted

## Context

The workflows should be real (OIDC, environments, approvals) so they can be reviewed and used, but
there is no subscription configured, and a portfolio repo must never deploy by accident.

## Decision

Every deploy and teardown job requires the repository variable `DEPLOY_ENABLED == 'true'`, which is
not set. The `preflight` job reports the gate. Azure login is OIDC only. Prod requires environment
reviewers, and teardown requires typing the environment name.

## Consequences

- Pushes to main stay green without Azure.
- Enabling deployment is a deliberate, documented step (docs/deployment.md).
