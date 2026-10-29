variable "function_name" {
  description = "Lambda function name. Also used for its IAM role and log group."
  type        = string
}

variable "source_dir" {
  description = "Directory with the function code. It is zipped as-is."
  type        = string
}

variable "handler" {
  description = "Function entry point."
  type        = string
  default     = "handler.handler"
}

variable "runtime" {
  description = "Lambda runtime."
  type        = string
  default     = "python3.13"
}

variable "timeout" {
  description = "Timeout in seconds."
  type        = number
  default     = 15
}

variable "memory_size" {
  description = "Memory in MB."
  type        = number
  default     = 256
}

variable "environment" {
  description = "Environment variables. Never put secret values here; pass secret names instead."
  type        = map(string)
  default     = {}
}

variable "policy_json" {
  description = "Inline IAM policy (JSON) with the function's own permissions, on top of basic logging."
  type        = string
  default     = null
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention."
  type        = number
  default     = 30
}

variable "tags" {
  description = "Extra tags (e.g. Service) added to the provider default tags."
  type        = map(string)
  default     = {}
}
