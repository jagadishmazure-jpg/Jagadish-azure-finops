# Interview guide

How I walk through this repo in 5, 15 or 30 minutes.

## 5 minutes

1. **The problem:** cost advice is easy to give and hard to trust.
2. **The answer:** ten patterns as code, each with evidence, a decision rule, a skip list and the
   math. Run `finops estate`: $6,159.31 a month of proposed savings on a $12,696.61 estate, every
   pattern reconciled to the FOCUS bill.
3. **The guardrail:** the FinOps agent proposes, people approve, the executor only prints.
4. **AI:** the eval gate. "Everything on the small model" would save 94% and is blocked.

## 15 minutes

Add one pattern in depth. Good choices:

- **Commitments (p03):** commit to the floor, not the average; brute force agrees with the analytic
  rule; term policy chooses 1 year at 13 units; break-even 7.4 months.
- **Serverless (p07):** the idle WS1 plan story, and the telemetry function that must stay on its
  plan because consumption would be $3,282.30 a month.
- **Idle cleanup (p08):** grace periods, exempt tag, snapshot first, two approvers, digest-bound
  approval. Show `finops mcp-demo`.

## 30 minutes

Add AI FinOps and the real-subscription path:

- Attribution reconciles to the bill with a $0.00 gap.
- Routing fails safe; caches are per tenant and match entity numbers.
- Budgets degrade, then block, and never cut off a critical agent.
- PTU: 15 units at $10,950 a month cannot break even for this workload.
- ROI: one use case is negative and cheaper tokens will not fix it.
- Read-only roles for a real subscription, and why the executor will never be live.

## Questions to expect

| Question | Short answer |
|---|---|
| Why not just use Advisor? | Advisor is the first list. This adds memory, projected peaks, licence pools, both-ways serverless pricing, approvals and reconciliation. |
| How do you avoid breaking things? | Read-only access, reversible first, skip lists, grace periods, approvals bound to a digest, dry-run executor. |
| How sure are the numbers? | List prices from a snapshot; estimates labelled; every pattern reconciled to the bill. |
| Reservation or savings plan? | Reservation when the family is stable and cheaper; savings plan wins ties because it is flexible. |
| What would you do first at a client? | FOCUS export, tag compliance in dollars, budgets, idle queries: crawl first (see finops-maturity.md). |
| How do you cut AI cost without hurting quality? | Attribute, then route, cache and right-model behind an eval gate with a quality budget. |
