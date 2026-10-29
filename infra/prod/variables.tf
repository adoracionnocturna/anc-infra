variable "aws_account_id" {
  description = "AWS account ID Terraform is allowed to operate on. Provided via TF_VAR_aws_account_id."
  type        = string
  sensitive   = true
}
