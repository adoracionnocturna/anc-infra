# Shared user directory for ANC web apps. No self sign-up and no emails: an administrator creates
# every user and resets forgotten passwords. Access to each app is granted through groups.
# Docs: docs/api/README.md#users-and-access

resource "aws_cognito_user_pool" "users" {
  name                = "${local.name_prefix}-users"
  username_attributes = ["email"]
  deletion_protection = "ACTIVE"
  mfa_configuration   = "OFF"

  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "admin_only"
      priority = 1
    }
  }

  password_policy {
    minimum_length                   = 12
    require_lowercase                = true
    require_uppercase                = true
    require_numbers                  = true
    require_symbols                  = true
    temporary_password_validity_days = 7
  }

  tags = { Service = "auth" }
}

# Browser app client (public: no client secret). Sign-in with SRP; refresh tokens can be revoked.
resource "aws_cognito_user_pool_client" "insights_web" {
  name         = "${local.name_prefix}-insights-web"
  user_pool_id = aws_cognito_user_pool.users.id

  generate_secret               = false
  explicit_auth_flows           = ["ALLOW_USER_SRP_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]
  prevent_user_existence_errors = "ENABLED"
  enable_token_revocation       = true

  access_token_validity  = 1
  id_token_validity      = 1
  refresh_token_validity = 7

  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }
}
