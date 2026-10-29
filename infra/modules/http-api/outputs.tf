output "api_endpoint" {
  description = "Base invoke URL of the API."
  value       = trimsuffix(aws_apigatewayv2_stage.default.invoke_url, "/")
}
