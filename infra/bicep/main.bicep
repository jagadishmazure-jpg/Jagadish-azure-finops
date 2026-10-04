// Azure FinOps guardrails (Bicep twin of infra/terraform): policy definitions at subscription
// scope, then a resource group with policy assignments, an action group, a budget, a storage
// account with a lifecycle policy and an opt-in autoscale demo. Smallest settings everywhere.
targetScope = 'subscription'

@allowed(['dev', 'prod'])
param environment string = 'dev'
@allowed(['eastus2', 'westus2', 'westeurope'])
param location string = 'eastus2'
@description('Monthly budget for the FinOps resource group')
param monthlyBudget int = 10
@description('Receives budget alerts; pass it at deploy time, never commit a real address')
param alertEmail string = 'finops-alerts@example.com'
@allowed(['Audit', 'Deny', 'Disabled'])
param policyEffect string = 'Audit'
param allowedVmSkus array = ['Standard_B2s', 'Standard_D2s_v5', 'Standard_D4s_v5', 'Standard_E4s_v5']
@description('Creates a P0v3 plan with autoscale (bills while it exists)')
param deployAutoscaleDemo bool = false
@description('First day of the budget period; defaults to the current month')
param budgetStartDate string = utcNow('yyyy-MM-01')

var region = { eastus2: 'eus2', westus2: 'wus2', westeurope: 'weu' }[location]
var suffix = '${environment}-${region}-001'
var tags = {
  env: environment
  owner: 'platform-team'
  app: 'azure-finops'
  'cost-center': 'CC-4004'
  'managed-by': 'bicep'
}

module policies 'modules/policies.bicep' = {
  name: 'finops-policies'
}

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-finops-${suffix}'
  location: location
  tags: tags
}

module guardrails 'modules/guardrails.bicep' = {
  name: 'finops-guardrails'
  scope: rg
  params: {
    location: location
    suffix: suffix
    environment: environment
    region: region
    tags: tags
    monthlyBudget: monthlyBudget
    alertEmail: alertEmail
    policyEffect: policyEffect
    allowedVmSkus: allowedVmSkus
    deployAutoscaleDemo: deployAutoscaleDemo
    budgetStartDate: budgetStartDate
    policyDefinitionIds: policies.outputs.ids
  }
}

output AZURE_RESOURCE_GROUP string = rg.name
output STORAGE_ACCOUNT string = guardrails.outputs.storageAccount
