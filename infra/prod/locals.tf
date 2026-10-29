locals {
  aws_region = "us-east-1"
  repository = "adoracionnocturna/anc-infra"

  common_tags = {
    ManagedBy   = "terraform"
    Environment = "prod"
    Project     = "anc"
    Repository  = local.repository
  }
}
