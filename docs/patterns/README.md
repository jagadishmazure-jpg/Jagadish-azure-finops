# `docs/patterns/`

One doc per pattern, each with the same 13 sections: problem, signals, detection logic, decision rule, worked example, savings math, risks and guardrails, automation and approval, IaC and policy, observability and KQL, Azure tools, limitations, interview talking points.

| File | What it does |
|---|---|
| [`01-rightsize.md`](01-rightsize.md) | Rightsize VMs and App Service plans on p95 CPU and memory |
| [`02-autoscale.md`](02-autoscale.md) | App Service autoscale, AKS autoscaler + HPA/KEDA, Container Apps scale to zero |
| [`03-commitments.md`](03-commitments.md) | Reservations and savings plans, sized to the floor |
| [`04-spot.md`](04-spot.md) | Spot for interruptible batch work with checkpoints |
| [`05-storage-tiering.md`](05-storage-tiering.md) | Lifecycle tiering hot, cool, cold, archive |
| [`06-hybrid-benefit.md`](06-hybrid-benefit.md) | Windows Server and SQL Server licence allocation |
| [`07-serverless.md`](07-serverless.md) | Consumption vs always-on plans, both ways |
| [`08-idle-cleanup.md`](08-idle-cleanup.md) | Orphans and idle resources behind approvals |
| [`09-tagging-chargeback.md`](09-tagging-chargeback.md) | Tag compliance, showback, chargeback, budgets |
| [`10-cache-egress.md`](10-cache-egress.md) | Front Door, Redis and incremental copies |
