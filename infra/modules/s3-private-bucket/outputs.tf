# Sensitive: globally unique bucket names include the account ID, and plans are shown in public CI logs.
output "bucket_name" {
  description = "Bucket name."
  value       = aws_s3_bucket.this.id
  sensitive   = true
}

output "bucket_arn" {
  description = "Bucket ARN."
  value       = aws_s3_bucket.this.arn
  sensitive   = true
}
