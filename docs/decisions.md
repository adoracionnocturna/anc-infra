# Decision log

Short, dated records of decisions that shape this repository. Newest first. Each entry: context, decision, consequences. Do not rewrite past entries; add a new one that supersedes them.

---

## 2026-10-30 — Storage summary endpoint; bucket identifiers sensitive

**Context.** The frontend needs to show how many raw submission files exist in S3 and in which folders, including forms that are stored only in S3.

**Decision.** `GET /insights/storage` in `insights-api` returns totals per form and per folder (count, bytes, last change). It never returns file names (they contain submission IDs), contents or the bucket name (it contains the account ID). The Lambda gets `s3:ListBucket` limited to the `submissions/` prefix and no `s3:GetObject`. The `s3-private-bucket` module now marks `bucket_name` and `bucket_arn` as sensitive so they never appear in plan diffs shown in public CI logs.

**Consequences.** S3-only forms (`leader-self-assessment`) expose file counts and sizes, not data. Listing is O(files); revisit (e.g. S3 Inventory) if the bucket grows to tens of thousands of files.

## 2026-10-30 — Insights API temporarily public

**Context.** Authentication is not critical yet, and the frontend needs to read the data now without a sign-in flow. Supersedes the enforcement part of "Insights read API" below.

**Decision.** The insights routes are public: `local.insights_require_auth = false` removes the JWT authorizer from the routes and the group check from the Lambda (no `READER_GROUP`). Cognito (pool, app client, group, authorizer) stays deployed and documented in [auth.md](auth.md), so turning authentication back on is a one-line change plus users. IAM, CORS, throttling and the S3-only exclusion of leader self-assessments stay as they are.

**Consequences.** Anyone with the API URL can read every participant feedback submission, including free-text answers; CORS does not prevent direct requests. The URL is kept out of the repository and CI logs, but a public frontend would reveal it. Turn authentication on before the frontend is shared beyond the team.

## 2026-10-30 — Admin-only CLI sign-in for testing

**Context.** Testing the insights API needs real Cognito tokens, and the AWS CLI cannot perform SRP.

**Decision.** The `anc-prod-insights-web` client also allows `ADMIN_USER_PASSWORD_AUTH`. It requires AWS credentials with `cognito-idp:AdminInitiateAuth`, so it adds no browser-facing sign-in path. Allowed users stay in Cognito only (pool + `insights-readers` group); email addresses are never stored in the repository or in GitHub variables or secrets.

**Consequences.** Administrators can test end to end from the CLI ([api/README.md](api/README.md#testing-from-the-command-line)).

## 2026-10-30 — Insights read API: shared HTTP API, Cognito users, group-based access

**Context.** A browser frontend (Vite + React) will read the participant feedback submissions to build insight charts. The data contains personal answers, and anything shipped to a browser is public, so API keys or static tokens are not acceptable.

**Decision.**
- **One HTTP API for all services** (`anc-prod-api`, `infra/prod/api.tf`). Each service file declares its integrations and routes in a local (`<service>_api`) and `api.tf` merges them. The former `anc-prod-youform-api` was moved (Terraform `moved` blocks, same API ID), so the YouForm webhook URL did not change. The `http-api` module now supports several Lambda integrations, an optional JWT authorizer and optional CORS.
- **Cognito user pool for people** (`anc-prod-users`, `infra/prod/auth.tf`), shared by future web apps: admin-created users only, no emails (recovery by an administrator), strong password policy, deletion protection. Each app gets its own public app client (SRP, no secret) and access is granted per app through groups (`insights-readers`).
- **Authorization in two layers**: API Gateway's native JWT authorizer validates the access token; the Lambda requires the group claim. IAM limits the Lambda to read-only access to the partitions of DynamoDB-stored forms. Forms stored only in S3 are never exposed.
- **Full submissions, not aggregates**, with light normalization (numbers, checkbox lists, sorted answers) so the frontend can compute any chart.
- **Contract documented** in [api/README.md](api/README.md) and [api/openapi.yaml](api/openapi.yaml).
- The deploy role may manage Cognito user pools only when tagged `Project=anc` (pool ARNs contain IDs, not names).
- Deterministic Lambda packages: `.gitattributes` forces LF, and `archive_file` excludes `__pycache__` (written by the tests) and fixes file modes, so packages built on Windows match the ones built in CI and unchanged code does not redeploy.

**Consequences.** MFA is off for now (no SMS/email); enable TOTP if the audience grows. CORS must list every frontend origin (`local.api_allowed_origins`). Removing a user's access takes effect when their current access token expires (at most 1 hour). Pool and client IDs appear in CI apply logs; they are public by nature (they ship in the frontend bundle).

## 2026-10-29 — Timestamps in Bogotá time

**Context.** YouForm sends timestamps in UTC. The people using the data are in Colombia, and UTC dates near midnight land on the wrong day or month.

**Decision.** Normalized timestamps (`started_at`, `completed_at`, `received_at` in DynamoDB) and the S3 `YYYY/MM` prefix use Bogotá time (UTC-5, no daylight saving time). Timestamps are ISO 8601 with explicit `-05:00` offset, so they remain exact instants. The raw payload in S3 is never modified.

**Consequences.** Records written before this change keep UTC timestamps until re-processed.

## 2026-10-29 — youform-intake design

**Context.** Two YouForm forms must be received: participant feedback (needs queryable data) and leader self-assessment (must only reach S3). Many more forms are expected.

**Decision.**
- One webhook, one Lambda, one bucket and one table shared by all forms; per-form behavior is configuration (`store_in_dynamodb`).
- Authentication with YouForm's webhook signing secrets (HMAC-SHA256 of the raw body), one per form, stored in Secrets Manager. The secret value is set outside Terraform so it never reaches the state.
- Every submission is stored raw in S3 (default SSE-S3 encryption, no KMS). Only flagged forms are normalized into DynamoDB; IAM enforces it with `dynamodb:LeadingKeys`.
- Form IDs come from GitHub variables (not committed) and are marked `sensitive` in Terraform. They are not masked in Actions logs; accepted because they are already public in the form links and the webhook requires a signature. The webhook URL is a sensitive output.
- Answers are keyed by YouForm field ID, not question text.
- Lambda code depends only on stdlib + `boto3`; packaged with `archive_file`.

**Consequences.** Adding a form needs a GitHub variable, a Terraform variable and a config entry, but no new infrastructure. Submissions are not deleted from YouForm by this service.

## 2026-10-29 — Terraform organization: building blocks + one file per service

**Context.** Many services and features are expected over time. A previous project used one module per service, which led to long chains of pass-through variables and a large root module.

**Decision.** Two layers only: generic building-block modules in `infra/modules/` and one composition file per service in `infra/prod/`. Features are configuration inside a service whenever possible. Lambdas are packaged with `archive_file`. Full rules in [terraform-guidelines.md](terraform-guidelines.md).

**Consequences.** Adding a form is a config change; adding a service is one new file plus its code. Modules are only extracted when a pattern repeats.

## 2026-10-29 — Account-specific values kept out of the public repository

**Context.** The repository is public and GitHub Actions logs are visible to anyone.

**Decision.** AWS account ID, deploy role ARN and state bucket name are provided through GitHub secrets (`AWS_ACCOUNT_ID`, `AWS_DEPLOY_ROLE_ARN`, `TF_STATE_BUCKET`). IAM policy files use an `<AWS_ACCOUNT_ID>` placeholder. Terraform does not output account identifiers. All repository content is in English.

**Consequences.** CI masks these values in logs. The state bucket is passed with `-backend-config` at init.

## 2026-10-29 — Single environment and single branch

**Context.** The project is small and there is no separate AWS environment for development.

**Decision.** Only `prod` and only `main`. A push to `main` runs `plan` and `apply` automatically.

**Consequences.** Validation happens locally before pushing (`fmt`, `validate`, `plan`, tests). Revisit if a second environment is created.

## 2026-10-29 — Dedicated OIDC deploy role scoped to `anc-*`

**Context.** The AWS account is shared with other projects, whose roles must not be modified.

**Decision.** A dedicated `GitHubActionsAncDeployRole`, created manually (see [../bootstrap/iam/](../bootstrap/iam/)), trusted only by this repository's `main` branch via GitHub's immutable OIDC subject, with permissions limited to `anc-*` resources.

**Consequences.** Every ANC resource must use the `anc-` prefix. New AWS services require updating the role policy in `bootstrap/iam/`.

## 2026-10-29 — Remote state in S3 with native locking

**Decision.** State in a dedicated, versioned, encrypted, private S3 bucket, key `prod/terraform.tfstate`, with `use_lockfile = true` (no DynamoDB lock table). The bucket is ensured by `infra/scripts/bootstrap-state-bucket.sh` before `terraform init`.
