# Decision log

Short, dated records of decisions that shape this repository. Newest first. Each entry: context, decision, consequences. Do not rewrite past entries; add a new one that supersedes them.

---

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
