# Azure FinOps guardrails: policy, budget + alerts, storage lifecycle and an (opt-in) autoscale demo.
# Smallest settings everywhere; nothing here runs workloads.

resource "azurerm_resource_group" "this" {
  name     = "rg-${local.short}-${local.suffix}"
  location = var.location
  tags     = local.tags
}

# --- Azure Policy: definitions from infra/policies/*.json, assigned to the resource group
resource "azurerm_policy_definition" "this" {
  for_each     = local.policies
  name         = "finops-${each.key}"
  policy_type  = "Custom"
  mode         = each.value.mode
  display_name = each.value.displayName
  description  = each.value.description
  metadata     = jsonencode(each.value.metadata)
  parameters   = jsonencode(each.value.parameters)
  policy_rule  = jsonencode(each.value.policyRule)
}

resource "azurerm_resource_group_policy_assignment" "this" {
  for_each             = local.policies
  name                 = "finops-${each.key}"
  resource_group_id    = azurerm_resource_group.this.id
  policy_definition_id = azurerm_policy_definition.this[each.key].id
  parameters           = jsonencode(local.policy_parameters[each.key])
}

# --- Alerts: one action group, used by the budget
resource "azurerm_monitor_action_group" "finops" {
  name                = "ag-${local.short}-${local.suffix}"
  resource_group_name = azurerm_resource_group.this.name
  short_name          = "finops"
  tags                = local.tags

  email_receiver {
    name                    = "finops-team"
    email_address           = var.alert_email
    use_common_alert_schema = true
  }
}

resource "azurerm_consumption_budget_resource_group" "this" {
  name              = "budget-${local.short}-${local.suffix}"
  resource_group_id = azurerm_resource_group.this.id
  amount            = var.monthly_budget
  time_grain        = "Monthly"

  time_period {
    start_date = formatdate("YYYY-MM-01'T'00:00:00Z", timestamp())
  }

  dynamic "notification" {
    for_each = local.budget_notifications
    content {
      enabled        = true
      threshold      = tonumber(notification.key)
      threshold_type = notification.value
      operator       = "GreaterThanOrEqualTo"
      contact_groups = [azurerm_monitor_action_group.finops.id]
    }
  }

  lifecycle {
    ignore_changes = [time_period] # the start month is fixed at creation
  }
}

# --- Storage with last-access tracking and a lifecycle (tiering) policy
resource "azurerm_storage_account" "lake" {
  name                            = substr(replace("st${local.short}${var.environment}${local.region}001", "-", ""), 0, 24)
  resource_group_name             = azurerm_resource_group.this.name
  location                        = var.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  shared_access_key_enabled       = false
  allow_nested_items_to_be_public = false
  tags                            = local.tags

  blob_properties {
    last_access_time_enabled = true
    delete_retention_policy {
      days = 7
    }
  }
}

resource "azurerm_storage_management_policy" "lake" {
  storage_account_id = azurerm_storage_account.lake.id

  rule {
    name    = "tier-by-last-access"
    enabled = true
    filters {
      blob_types   = ["blockBlob"]
      prefix_match = ["raw-telemetry/", "shipment-docs/"]
    }
    actions {
      base_blob {
        tier_to_cool_after_days_since_last_access_time_greater_than    = 30
        tier_to_cold_after_days_since_last_access_time_greater_than    = 90
        tier_to_archive_after_days_since_last_access_time_greater_than = 180
        auto_tier_to_hot_from_cool_enabled                             = true
      }
    }
  }
}

# --- Opt-in autoscale demo: smallest plan that supports autoscale, 1..2 instances
resource "azurerm_service_plan" "demo" {
  count               = var.deploy_autoscale_demo ? 1 : 0
  name                = "asp-${local.short}-${local.suffix}"
  resource_group_name = azurerm_resource_group.this.name
  location            = var.location
  os_type             = "Linux"
  sku_name            = "P0v3"
  worker_count        = 1
  tags                = local.tags
}

resource "azurerm_monitor_autoscale_setting" "demo" {
  count               = var.deploy_autoscale_demo ? 1 : 0
  name                = "autoscale-${local.short}-${local.suffix}"
  resource_group_name = azurerm_resource_group.this.name
  location            = var.location
  target_resource_id  = azurerm_service_plan.demo[0].id
  tags                = local.tags

  profile {
    name = "follow-demand"
    capacity {
      default = 1
      minimum = 1
      maximum = 2
    }
    rule {
      metric_trigger {
        metric_name        = "CpuPercentage"
        metric_resource_id = azurerm_service_plan.demo[0].id
        time_grain         = "PT1M"
        statistic          = "Average"
        time_window        = "PT10M"
        time_aggregation   = "Average"
        operator           = "GreaterThan"
        threshold          = 70
      }
      scale_action {
        direction = "Increase"
        type      = "ChangeCount"
        value     = "1"
        cooldown  = "PT5M"
      }
    }
    rule {
      metric_trigger {
        metric_name        = "CpuPercentage"
        metric_resource_id = azurerm_service_plan.demo[0].id
        time_grain         = "PT1M"
        statistic          = "Average"
        time_window        = "PT10M"
        time_aggregation   = "Average"
        operator           = "LessThan"
        threshold          = 35
      }
      scale_action {
        direction = "Decrease"
        type      = "ChangeCount"
        value     = "1"
        cooldown  = "PT15M"
      }
    }
  }
}
