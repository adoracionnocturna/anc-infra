# Sensitive so it never appears in public CI logs. Read it locally with:
#   terraform output -raw youform_webhook_url
output "youform_webhook_url" {
  description = "URL to configure as the webhook in YouForm."
  value       = "${module.youform_api.api_endpoint}/webhooks/youform"
  sensitive   = true
}
