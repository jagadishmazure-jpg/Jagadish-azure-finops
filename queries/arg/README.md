# `queries/arg/`

Azure Resource Graph (KQL dialect). Run with `az graph query -q "$(cat FILE)"`.

| File | What it does |
|---|---|
| [`unattached-disks.kql`](unattached-disks.kql) | Disks attached to nothing (p08) |
| [`unassociated-public-ips.kql`](unassociated-public-ips.kql) | Public IPs bound to nothing (p08) |
| [`orphaned-nics.kql`](orphaned-nics.kql) | NICs with no VM or endpoint (p08) |
| [`stopped-not-deallocated-vms.kql`](stopped-not-deallocated-vms.kql) | VMs stopped but still allocated (p08) |
| [`idle-app-service-plans.kql`](idle-app-service-plans.kql) | Plans with no sites (p07, p08) |
| [`container-apps-warm-replicas.kql`](container-apps-warm-replicas.kql) | Container Apps with minReplicas > 0 (p02, p08) |
| [`hybrid-benefit-candidates.kql`](hybrid-benefit-candidates.kql) | Windows and SQL VMs without AHB (p06) |
| [`storage-without-lifecycle.kql`](storage-without-lifecycle.kql) | Accounts without last-access tracking (p05) |
| [`untagged-resources.kql`](untagged-resources.kql) | Resources missing required tags (p09) |
| [`spot-ready-scale-sets.kql`](spot-ready-scale-sets.kql) | Scale sets on regular priority (p04) |
