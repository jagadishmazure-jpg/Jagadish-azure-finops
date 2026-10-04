# ADR 0003: Deterministic synthetic data for a fictional company

- **Status:** Accepted

## Context

Real cost exports and inventories contain subscription IDs, names and commercial terms. A
portfolio repo must not contain any of them, but the patterns need realistic shapes: daily cycles,
weekly spikes, orphans, untagged resources.

## Decision

Generate all inputs from seeded code (`src/finops/synth.py`) for a fictional company, Larkspur
Freight, check the output in, and verify it in CI with `generate_data.py --check`. The case study
uses its own small synthetic inventory with the shape of a real finding.

## Consequences

- Every run gives the same numbers, so docs can quote them.
- The data is plausible, not real; docs say so.
- Hygiene tests block real identifiers from being added.
