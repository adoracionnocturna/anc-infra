# Service catalog

Every service deployed from this repository. Update this file in the same commit that adds or changes a service.

| Service | Status | Entry point | Terraform | Code |
| --- | --- | --- | --- | --- |
| `youform-intake` | Active | `POST /webhooks/youform` from YouForm | `infra/prod/youform-intake.tf` | `services/youform_webhook/` |

---

## youform-intake

**Status:** active.

**Purpose.** Receive YouForm submissions through a signed webhook and store them. Every form keeps its raw payload in S3; selected forms also get a normalized record in DynamoDB.

**Entry point.** YouForm webhook → API Gateway HTTP API (`POST /webhooks/youform`, throttled) → Lambda `anc-prod-youform-webhook`. The webhook URL is a sensitive Terraform output (`youform_webhook_url`), never printed in CI.

**Features (forms).** Form IDs are not stored in the repository; they come from GitHub variables.

| Slug | Form | GitHub variable with the form ID | S3 | DynamoDB |
| --- | --- | --- | --- | --- |
| `participant-feedback` | Retroalimentación Participantes (Reinicialo II - 2026) | `YOUFORM_PARTICIPANT_FEEDBACK_FORM_ID` | yes | yes |
| `leader-self-assessment` | Autoevaluación Líderes (Reinicialo II - 2026) | `YOUFORM_LEADER_SELF_ASSESSMENT_FORM_ID` | yes | no |

**Request handling.**

1. Look up the form by `form_id`; unknown forms are rejected (`401`).
2. Verify the `Signature` header: hex HMAC-SHA256 of the raw body with that form's signing secret (`401` if invalid).
3. Store the raw body in S3, then (only if `store_in_dynamodb`) the normalized record in DynamoDB.
4. Respond `200`. Storage or configuration errors respond `500`, so YouForm retries. Writes are idempotent per `submission_id`.

**Resources.**

| Resource | Name |
| --- | --- |
| HTTP API | `anc-prod-youform-api` |
| Lambda + role + log group (30 days) | `anc-prod-youform-webhook` |
| S3 bucket (private, SSE-S3, versioned, TLS only) | `anc-prod-youform-submissions-<account_id>-us-east-1` |
| DynamoDB table (on-demand, PITR, deletion protection) | `anc-prod-youform-responses` |
| Secrets Manager | `anc/prod/youform-intake` |

The Lambda role can only write `submissions/*` in S3, and its DynamoDB `PutItem` is restricted (`dynamodb:LeadingKeys`) to forms with `store_in_dynamodb = true`.

**Data layout.**

- S3: `submissions/<slug>/<YYYY>/<MM>/<submission_id>.json`, the request body exactly as received (YouForm timestamps stay in UTC there). `YYYY/MM` come from `completed_at` in Bogotá time (falls back to the receive time).
- DynamoDB: `pk = FORM#<form_id>`, `sk = SUBMISSION#<submission_id>`. Attributes: `form_id`, `form_slug`, `form_name`, `submission_id`, `started_at`, `completed_at`, `received_at`, `raw_s3_key`, `answers`. `answers` is a map keyed by YouForm field ID: `{question, type, answer, position}`. Keying by field ID keeps records stable when question text is edited.
- Timestamps in DynamoDB are ISO 8601 in Bogotá time with explicit offset, e.g. `2026-10-29T19:57:28-05:00`. YouForm sends UTC (`...Z`); values that cannot be parsed are stored as received.

**Setup of a form's webhook.**

1. Generate a signing secret, e.g. `openssl rand -hex 32`.
2. Add it to the secret `anc/prod/youform-intake` (JSON object `{"<form_id>": "<signing secret>", ...}`):
   ```bash
   aws secretsmanager put-secret-value --secret-id anc/prod/youform-intake \
     --secret-string '{"<form_id_1>":"<secret_1>","<form_id_2>":"<secret_2>"}'
   ```
3. Get the URL locally: `terraform output -raw youform_webhook_url`.
4. In YouForm, add a webhook to the form with that URL and the same signing secret. The test delivery must return `200`.

Add the secret before creating the webhook: YouForm disables a webhook whose test delivery fails.

**Operations.**

- Logs: CloudWatch log group `/aws/lambda/anc-prod-youform-webhook`. Logs carry form slug, submission ID and outcome, never answers.
- Failed deliveries: YouForm retries non-2xx responses automatically and keeps delivery logs for 15 days, with a manual retry button.
- Adding a form: new GitHub variable with the form ID, new variable in `infra/prod/variables.tf` and workflow `env`, new entry in `local.youform_forms`, new key in the signing-secret JSON.

---

## Template for a new service

```markdown
## <service-name>

**Status:** planned | active | deprecated.

**Purpose.** One or two sentences.

**Entry point.** Webhook / schedule / queue, and who calls it.

**Features.** Configured variants (forms, sources, ...).

**Resources.** AWS resources and their names (without account IDs).

**Data layout.** Keys, S3 prefixes, retention.

**Operations.** Where to look when it fails (log group, alarms), how to re-process.
```
