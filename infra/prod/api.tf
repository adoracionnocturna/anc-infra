# Shared HTTP API for every ANC service. Each service file declares its integrations and routes
# in a local (`<service>_api`); this file only merges them.
# Docs: docs/api/README.md

locals {
  # Browser origins allowed to call the API (CORS). Add the production frontend origin here.
  api_allowed_origins = ["http://localhost:5173"]
}

module "api" {
  source = "../modules/http-api"

  name = "${local.name_prefix}-api"

  integrations = merge(
    local.youform_intake_api.integrations,
    local.insights_api.integrations,
  )

  routes = merge(
    local.youform_intake_api.routes,
    local.insights_api.routes,
  )

  # Routes with `authorized = true` require a Cognito access token from an allowed app client (auth.tf).
  jwt_authorizer = {
    issuer   = "https://${aws_cognito_user_pool.users.endpoint}"
    audience = [aws_cognito_user_pool_client.insights_web.id]
  }

  cors = {
    allow_origins = local.api_allowed_origins
    allow_methods = ["GET"]
    allow_headers = ["authorization"]
  }

  tags = { Service = "api" }
}

# The API used to belong to youform-intake (module.youform_api). Keeping its state keeps the same
# API ID, so the webhook URL configured in YouForm does not change. Safe to delete after one apply.
moved {
  from = module.youform_api.aws_apigatewayv2_api.this
  to   = module.api.aws_apigatewayv2_api.this
}

moved {
  from = module.youform_api.aws_apigatewayv2_stage.default
  to   = module.api.aws_apigatewayv2_stage.default
}

moved {
  from = module.youform_api.aws_apigatewayv2_integration.lambda
  to   = module.api.aws_apigatewayv2_integration.this["youform_webhook"]
}

moved {
  from = module.youform_api.aws_apigatewayv2_route.this["POST /webhooks/youform"]
  to   = module.api.aws_apigatewayv2_route.this["POST /webhooks/youform"]
}

moved {
  from = module.youform_api.aws_lambda_permission.api_gateway
  to   = module.api.aws_lambda_permission.this["youform_webhook"]
}
