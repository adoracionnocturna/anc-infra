variable "bucket_name" {
  description = "Globally unique bucket name."
  type        = string
}

variable "versioning_enabled" {
  description = "Keep previous versions of overwritten or deleted objects."
  type        = bool
  default     = true
}

variable "tags" {
  description = "Extra tags (e.g. Service) added to the provider default tags."
  type        = map(string)
  default     = {}
}
