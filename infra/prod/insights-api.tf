# insights-api: authenticated, read-only access to YouForm submissions stored in DynamoDB,
# for the insights frontend. Routes live on the shared API (api.tf) behind the Cognito JWT authorizer.
# Docs: docs/services/README.md#insights-api, docs/api/README.md

locals {
  insights_reader_group = "insights-readers"

  # Readable forms: only those normalized into DynamoDB, as {slug: form_id}.
  insights_forms = { for id, form in local.youform_forms : form.slug => id if form.store_in_dynamodb }

  insights_tags = { Service = "insights-api" }

  insights_api = {
    integrations = {
      insights_api = { function_name = module.insights_api.function_name, invoke_arn = module.insights_api.invoke_arn }
    }
    routes = {
      "GET /insights/forms"                                    = { integration = "insights_api", authorized = true }
      "GET /insights/forms/{form}/submissions"                 = { integration = "insights_api", authorized = true }
      "GET /insights/forms/{form}/submissions/{submission_id}" = { integration = "insights_api", authorized = true }
    }
  }
}

resource "aws_cognito_user_group" "insights_readers" {
  name         = local.insights_reader_group
  user_pool_id = aws_cognito_user_pool.users.id
  description  = "Can read form submissions through the insights API."
}

module "insights_api" {
  source = "../modules/lambda-function"

  function_name = "${local.name_prefix}-insights-api"
  source_dir    = "${local.services_dir}/insights_api/src"
  tags          = local.insights_tags

  environment = {
    FORMS_CONFIG    = jsonencode(local.insights_forms)
    RESPONSES_TABLE = aws_dynamodb_table.youform_responses.name
    READER_GROUP    = local.insights_reader_group
  }

  policy_json = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # Read-only, and only the partitions of readable forms.
        Sid      = "ReadResponsesOfReadableForms"
        Effect   = "Allow"
        Action   = ["dynamodb:Query", "dynamodb:GetItem"]
        Resource = aws_dynamodb_table.youform_responses.arn
        Condition = {
          "ForAllValues:StringEquals" = {
            "dynamodb:LeadingKeys" = [for id in values(local.insights_forms) : "FORM#${id}"]
          }
        }
      }
    ]
  })
}
