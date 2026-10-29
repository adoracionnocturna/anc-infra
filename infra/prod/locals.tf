locals {
  aws_region  = "us-east-1"
  environment = "prod"
  name_prefix = "anc-${local.environment}"
  repository  = "adoracionnocturna/anc-infra"

  # Global S3 names need a unique suffix. Marked sensitive so the account ID never shows in plans.
  bucket_suffix = sensitive("${data.aws_caller_identity.current.account_id}-${local.aws_region}")

  services_dir = "${path.root}/../../services"

  common_tags = {
    ManagedBy   = "terraform"
    Environment = local.environment
    Project     = "anc"
    Repository  = local.repository
  }
}

data "aws_caller_identity" "current" {}
