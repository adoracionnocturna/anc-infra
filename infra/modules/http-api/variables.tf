variable "name" {
  description = "HTTP API name."
  type        = string
}

variable "integrations" {
  description = "Lambda functions behind the API, keyed by a short name used in `routes`."
  type = map(object({
    function_name = string
    invoke_arn    = string
  }))
}

variable "routes" {
  description = "Routes keyed by route key (e.g. \"GET /items/{id}\"). `integration` is a key of `integrations`; `authorized` requires a valid JWT."
  type = map(object({
    integration = string
    authorized  = optional(bool, false)
  }))

  validation {
    condition     = alltrue([for route in values(var.routes) : contains(keys(var.integrations), route.integration)])
    error_message = "Every route must reference a key of `integrations`."
  }

  validation {
    condition     = var.jwt_authorizer != null || !anytrue([for route in values(var.routes) : route.authorized])
    error_message = "Authorized routes require `jwt_authorizer`."
  }
}

variable "jwt_authorizer" {
  description = "JWT authorizer for routes with `authorized = true` (e.g. a Cognito user pool). Null disables it."
  type = object({
    issuer   = string
    audience = list(string)
  })
  default = null
}

variable "cors" {
  description = "CORS for browser clients. Null disables it."
  type = object({
    allow_origins = list(string)
    allow_methods = list(string)
    allow_headers = list(string)
  })
  default = null
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
