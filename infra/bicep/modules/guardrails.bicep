// Resource-group guardrails: policy assignments, action group, budget, lifecycle storage, autoscale demo.
param location string
param suffix string
@allowed(['dev', 'prod'])
param environment string
@allowed(['eus2', 'wus2', 'weu'])
param region string
param tags object
param monthlyBudget int
param alertEmail string
param policyEffect string
param allowedVmSkus array
param deployAutoscaleDemo bool
param budgetStartDate string
param policyDefinitionIds object

var assignmentParams = {
  'require-tags': { effect: { value: policyEffect } }
  'allowed-vm-skus': { effect: { value: policyEffect }, allowedSkus: { value: allowedVmSkus } }
  'deny-untagged-public-ip': { effect: { value: policyEffect } }
}

resource assignments 'Microsoft.Authorization/policyAssignments@2024-04-01' = [for p in items(policyDefinitionIds): {
  name: 'finops-${p.key}'
  properties: {
    policyDefinitionId: p.value
    parameters: assignmentParams[p.key]
  }
}]

resource actionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = {
  name: 'ag-finops-${suffix}'
  location: 'global'
  tags: tags
  properties: {
    groupShortName: 'finops'
    enabled: true
    emailReceivers: [
      { name: 'finops-team', emailAddress: alertEmail, useCommonAlertSchema: true }
    ]
  }
}

var thresholds = [
  { pct: 50, type: 'Actual' }
  { pct: 80, type: 'Actual' }
  { pct: 100, type: 'Actual' }
  { pct: 110, type: 'Forecasted' }
]

resource budget 'Microsoft.Consumption/budgets@2023-11-01' = {
  name: 'budget-finops-${suffix}'
  properties: {
    category: 'Cost'
    amount: monthlyBudget
    timeGrain: 'Monthly'
    timePeriod: { startDate: budgetStartDate }
    notifications: toObject(thresholds, t => 'n${t.pct}${t.type}', t => {
      enabled: true
      operator: 'GreaterThanOrEqualTo'
      threshold: t.pct
      thresholdType: t.type
      contactGroups: [actionGroup.id]
    })
  }
}

resource lake 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: 'stfinops${environment}${region}001'
  location: location
  tags: tags
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowSharedKeyAccess: false
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: lake
  name: 'default'
  properties: {
    lastAccessTimeTrackingPolicy: { enable: true, name: 'AccessTimeTracking', trackingGranularityInDays: 1, blobType: ['blockBlob'] }
    deleteRetentionPolicy: { enabled: true, days: 7 }
  }
}

resource lifecycle 'Microsoft.Storage/storageAccounts/managementPolicies@2023-05-01' = {
  parent: lake
  name: 'default'
  dependsOn: [blobService]
  properties: {
    policy: {
      rules: [
        {
          name: 'tier-by-last-access'
          enabled: true
          type: 'Lifecycle'
          definition: {
            filters: { blobTypes: ['blockBlob'], prefixMatch: ['raw-telemetry/', 'shipment-docs/'] }
            actions: {
              baseBlob: {
                tierToCool: { daysAfterLastAccessTimeGreaterThan: 30 }
                tierToCold: { daysAfterLastAccessTimeGreaterThan: 90 }
                tierToArchive: { daysAfterLastAccessTimeGreaterThan: 180 }
                enableAutoTierToHotFromCool: true
              }
            }
          }
        }
      ]
    }
  }
}

resource plan 'Microsoft.Web/serverfarms@2023-12-01' = if (deployAutoscaleDemo) {
  name: 'asp-finops-${suffix}'
  location: location
  tags: tags
  kind: 'linux'
  sku: { name: 'P0v3', capacity: 1 }
  properties: { reserved: true }
}

resource autoscale 'Microsoft.Insights/autoscalesettings@2022-10-01' = if (deployAutoscaleDemo) {
  name: 'autoscale-finops-${suffix}'
  location: location
  tags: tags
  properties: {
    enabled: true
    targetResourceUri: plan.id
    profiles: [
      {
        name: 'follow-demand'
        capacity: { minimum: '1', maximum: '2', default: '1' }
        rules: [
          {
            metricTrigger: {
              metricName: 'CpuPercentage'
              metricResourceUri: plan.id
              timeGrain: 'PT1M'
              statistic: 'Average'
              timeWindow: 'PT10M'
              timeAggregation: 'Average'
              operator: 'GreaterThan'
              threshold: 70
            }
            scaleAction: { direction: 'Increase', type: 'ChangeCount', value: '1', cooldown: 'PT5M' }
          }
          {
            metricTrigger: {
              metricName: 'CpuPercentage'
              metricResourceUri: plan.id
              timeGrain: 'PT1M'
              statistic: 'Average'
              timeWindow: 'PT10M'
              timeAggregation: 'Average'
              operator: 'LessThan'
              threshold: 35
            }
            scaleAction: { direction: 'Decrease', type: 'ChangeCount', value: '1', cooldown: 'PT15M' }
          }
        ]
      }
    ]
  }
}

output storageAccount string = lake.name
output assignmentCount int = length(assignments)
