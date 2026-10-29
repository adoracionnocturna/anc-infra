# The bucket is passed at init time: terraform init -backend-config="bucket=<state bucket>"
terraform {
  backend "s3" {
    key          = "prod/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}
