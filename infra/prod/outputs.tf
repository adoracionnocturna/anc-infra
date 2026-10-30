# Outputs are sensitive so they never appear in public CI logs. Read them locally with:
#   terraform output -raw youform_webhook_url
#   terraform output -json insights_web_config
output "youform_webhook_url" {
  description = "URL to configure as the webhook in YouForm."
  value       = "${module.api.api_endpoint}/webhooks/youform"
  sensitive   = true
}

output "insights_web_config" {
  description = "Values the insights frontend needs (Vite environment variables)."
  value = {
    VITE_API_URL              = module.api.api_endpoint
    VITE_AWS_REGION           = local.aws_region
    VITE_COGNITO_USER_POOL_ID = aws_cognito_user_pool.users.id
    VITE_COGNITO_CLIENT_ID    = aws_cognito_user_pool_client.insights_web.id
  }
  sensitive = true
}
