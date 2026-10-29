variable "name" {
  description = "HTTP API name."
  type        = string
}

variable "lambda_function_name" {
  description = "Lambda function that handles every route."
  type        = string
}

variable "lambda_invoke_arn" {
  description = "Invoke ARN of that Lambda function."
  type        = string
}

variable "route_keys" {
  description = "Routes sent to the Lambda function, e.g. [\"POST /webhooks/youform\"]."
  type        = list(string)
}

variable "throttling_burst_limit" {
  description = "Maximum concurrent requests before throttling."
  type        = number
  default     = 20
}

variable "throttling_rate_limit" {
  description = "Steady-state requests per second."
  type        = number
  default     = 10
}

variable "tags" {
  description = "Extra tags (e.g. Service) added to the provider default tags."
  type        = map(string)
  default     = {}
}
