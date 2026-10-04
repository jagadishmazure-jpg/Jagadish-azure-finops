output "AZURE_RESOURCE_GROUP" {
  value = azurerm_resource_group.this.name
}

output "STORAGE_ACCOUNT" {
  value = azurerm_storage_account.lake.name
}

output "POLICY_DEFINITION_IDS" {
  value = { for k, v in azurerm_policy_definition.this : k => v.id }
}

output "BUDGET_ID" {
  value = azurerm_consumption_budget_resource_group.this.id
}
