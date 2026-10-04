# ADR 0005: AI cost cuts ship only through an eval gate

- **Status:** Accepted

## Context

The cheapest AI configuration is usually the worst one. Model routing, caching and smaller models
all save money and can all lower answer quality or leak data.

## Decision

Describe every AI optimization as a candidate with a cost and a quality score on the same eval
set as the baseline. `eval_gate.gate` blocks any candidate that drops quality by more than 1.0 point
or has a safety regression, whatever it saves.

## Consequences

- Big savings can be blocked (all-small-model, loose semantic cache), and the report shows why.
- Quality here is simulated; a real deployment must plug in its own golden set and judge.
