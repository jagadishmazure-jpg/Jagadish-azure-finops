# ADR 0004: The agent proposes; people approve; execution is a dry run

- **Status:** Accepted

## Context

An agent that can delete resources or buy reservations is a risk no matter how good its
analysis is. Prompt-level instructions ("ask before deleting") are not a control.

## Decision

Enforce approval in code. Plans have a SHA-256 digest; approvals bind to it, expire after 72 hours,
cannot come from the requester, need two distinct people for irreversible steps and a finance role
for purchases. The MCP server exposes no approve tool. The executor runs only in dry-run mode and
live execution raises `NotImplementedError`. Every step is written to a hash-chained audit log.

## Consequences

- The agent is safe to connect to any assistant.
- Applying a change is a human step through normal change management.
- Tests cover every refusal path.
