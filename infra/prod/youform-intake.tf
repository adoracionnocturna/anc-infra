# youform-intake: receives signed YouForm webhooks and stores submissions.
# Every form: raw payload in S3. Only forms with store_in_dynamodb = true: normalized record in DynamoDB.
# Docs: docs/services/README.md#youform-intake

locals {
  youform_intake_name = "${local.name_prefix}-youform"

  # Allowlist of accepted forms, keyed by YouForm form ID (IDs come from GitHub variables).
  # Adding a form = a form ID variable + an entry here + its signing secret.
  youform_forms = {
    (var.youform_participant_feedback_form_id)   = { slug = "participant-feedback", store_in_dynamodb = true }
    (var.youform_leader_self_assessment_form_id) = { slug = "leader-self-assessment", store_in_dynamodb = false }
  }

  youform_dynamodb_form_ids = [for id, form in local.youform_forms : id if form.store_in_dynamodb]

  youform_tags = { Service = "youform-intake" }
}

# Signing secrets, one per form: {"<form_id>": "<secret>"}. The value is set outside Terraform.
resource "aws_secretsmanager_secret" "youform_intake" {
  name                    = "anc/${local.environment}/youform-intake"
  description             = "YouForm webhook signing secrets, keyed by form ID."
  recovery_window_in_days = 7

  tags = local.youform_tags
}

module "youform_submissions_bucket" {
  source = "../modules/s3-private-bucket"

  bucket_name = "${local.youform_intake_name}-submissions-${local.bucket_suffix}"
  tags        = local.youform_tags
}

resource "aws_dynamodb_table" "youform_responses" {
  name                        = "${local.youform_intake_name}-responses"
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "pk"
  range_key                   = "sk"
  deletion_protection_enabled = true

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = local.youform_tags
}

module "youform_webhook" {
  source = "../modules/lambda-function"

  function_name = "${local.youform_intake_name}-webhook"
  source_dir    = "${local.services_dir}/youform_webhook/src"
  tags          = local.youform_tags

  environment = {
    FORMS_CONFIG       = jsonencode(local.youform_forms)
    SECRET_ID          = aws_secretsmanager_secret.youform_intake.name
    SUBMISSIONS_BUCKET = module.youform_submissions_bucket.bucket_name
    RESPONSES_TABLE    = aws_dynamodb_table.youform_responses.name
  }

  policy_json = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ReadSigningSecrets"
        Effect   = "Allow"
        Action   = "secretsmanager:GetSecretValue"
        Resource = aws_secretsmanager_secret.youform_intake.arn
      },
      {
        Sid      = "WriteRawSubmissions"
        Effect   = "Allow"
        Action   = "s3:PutObject"
        Resource = "${module.youform_submissions_bucket.bucket_arn}/submissions/*"
      },
      {
        # Only forms flagged store_in_dynamodb can be written, enforced by partition key.
        Sid      = "WriteResponsesOfAllowedForms"
        Effect   = "Allow"
        Action   = "dynamodb:PutItem"
        Resource = aws_dynamodb_table.youform_responses.arn
        Condition = {
          "ForAllValues:StringEquals" = {
            "dynamodb:LeadingKeys" = [for id in local.youform_dynamodb_form_ids : "FORM#${id}"]
          }
        }
      }
    ]
  })
}

module "youform_api" {
  source = "../modules/http-api"

  name                 = "${local.youform_intake_name}-api"
  lambda_function_name = module.youform_webhook.function_name
  lambda_invoke_arn    = module.youform_webhook.invoke_arn
  route_keys           = ["POST /webhooks/youform"]
  tags                 = local.youform_tags
}
