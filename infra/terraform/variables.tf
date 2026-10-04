variable "environment" {
  description = "dev or prod"
  type        = string
  default     = "dev"
  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "environment must be dev or prod"
  }
}

variable "location" {
  description = "Azure region"
  type        = string
  default     = "eastus2"
}

variable "monthly_budget" {
  description = "Monthly budget in the billing currency for the FinOps resource group"
  type        = number
  default     = 10
}

variable "alert_email" {
  description = "Email that receives budget and cost alerts (set through a pipeline variable, never committed)"
  type        = string
  default     = "finops-alerts@example.com"
}

variable "policy_effect" {
  description = "Audit while rolling out, Deny once the estate is clean"
  type        = string
  default     = "Audit"
  validation {
    condition     = contains(["Audit", "Deny", "Disabled"], var.policy_effect)
    error_message = "policy_effect must be Audit, Deny or Disabled"
  }
}

variable "allowed_vm_skus" {
  description = "VM sizes the allowed-SKU policy accepts"
  type        = list(string)
  default     = ["Standard_B2s", "Standard_D2s_v5", "Standard_D4s_v5", "Standard_E4s_v5"]
}

variable "deploy_autoscale_demo" {
  description = "Create a P0v3 plan with an autoscale setting (bills while it exists, so off by default)"
  type        = bool
  default     = false
}

variable "tags" {
  description = "Extra tags merged into the required ones"
  type        = map(string)
  default     = {}
}
