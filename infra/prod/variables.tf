variable "aws_account_id" {
  description = "AWS account ID Terraform is allowed to operate on. Provided via TF_VAR_aws_account_id."
  type        = string
  sensitive   = true
}

variable "youform_participant_feedback_form_id" {
  description = "YouForm form ID of the participant feedback form. Provided via GitHub variable."
  type        = string
  sensitive   = true
}

variable "youform_leader_self_assessment_form_id" {
  description = "YouForm form ID of the leader self-assessment form. Provided via GitHub variable."
  type        = string
  sensitive   = true
}
