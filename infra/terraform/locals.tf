locals {
  short  = "finops"
  region = { eastus2 = "eus2", westus2 = "wus2", westeurope = "weu" }[var.location]
  suffix = "${var.environment}-${local.region}-001"
  tags = merge({
    "env"         = var.environment
    "owner"       = "platform-team"
    "app"         = "azure-finops"
    "cost-center" = "CC-4004"
    "managed-by"  = "terraform"
  }, var.tags)
  # threshold (% of budget) => Actual or Forecasted spend
  budget_notifications = { "50" = "Actual", "80" = "Actual", "100" = "Actual", "110" = "Forecasted" }
  policies = {
    "require-tags"            = jsondecode(file("${path.module}/../policies/require-tags.json"))
    "allowed-vm-skus"         = jsondecode(file("${path.module}/../policies/allowed-vm-skus.json"))
    "deny-untagged-public-ip" = jsondecode(file("${path.module}/../policies/deny-untagged-public-ip.json"))
  }
  policy_parameters = {
    "require-tags"            = { effect = { value = var.policy_effect } }
    "allowed-vm-skus"         = { effect = { value = var.policy_effect }, allowedSkus = { value = var.allowed_vm_skus } }
    "deny-untagged-public-ip" = { effect = { value = var.policy_effect } }
  }
}
