# Offline plan tests: mocked provider, no Azure credentials, nothing created.
#   terraform init -backend=false && terraform test
mock_provider "azurerm" {
  mock_data "azurerm_client_config" {
    defaults = {
      tenant_id       = "00000000-0000-0000-0000-000000000001"
      subscription_id = "00000000-0000-0000-0000-000000000002"
      object_id       = "00000000-0000-0000-0000-000000000003"
    }
  }
}

run "dev_guardrails" {
  command = plan

  variables {
    environment = "dev"
  }

  assert {
    condition     = azurerm_resource_group.this.name == "rg-finops-dev-eus2-001"
    error_message = "resource group must follow the CAF naming pattern"
  }

  assert {
    condition     = alltrue([for k in ["cost-center", "owner", "env", "app"] : contains(keys(azurerm_resource_group.this.tags), k)])
    error_message = "the module must carry every tag its own policy requires"
  }

  assert {
    condition     = length(azurerm_policy_definition.this) == 3 && length(azurerm_resource_group_policy_assignment.this) == 3
    error_message = "three policy definitions, each assigned"
  }

  assert {
    condition     = jsondecode(azurerm_resource_group_policy_assignment.this["require-tags"].parameters).effect.value == "Audit"
    error_message = "dev audits first"
  }

  assert {
    condition     = azurerm_consumption_budget_resource_group.this.amount == 10 && length(local.budget_notifications) == 4 && local.budget_notifications["110"] == "Forecasted"
    error_message = "budget with four notifications (50/80/100 actual, 110 forecast)"
  }

  assert {
    condition     = azurerm_storage_account.lake.blob_properties[0].last_access_time_enabled && !azurerm_storage_account.lake.shared_access_key_enabled
    error_message = "tiering on last access needs tracking; keys stay off"
  }

  assert {
    condition     = length(azurerm_service_plan.demo) == 0 && length(azurerm_monitor_autoscale_setting.demo) == 0
    error_message = "the autoscale demo bills, so it is off unless asked for"
  }
}

run "prod_denies" {
  command = plan

  variables {
    environment           = "prod"
    policy_effect         = "Deny"
    deploy_autoscale_demo = true
  }

  assert {
    condition     = jsondecode(azurerm_resource_group_policy_assignment.this["deny-untagged-public-ip"].parameters).effect.value == "Deny"
    error_message = "prod denies"
  }

  assert {
    condition     = azurerm_service_plan.demo[0].sku_name == "P0v3" && azurerm_monitor_autoscale_setting.demo[0].profile[0].capacity[0].maximum == 2
    error_message = "autoscale demo uses the smallest plan and at most 2 instances"
  }
}
