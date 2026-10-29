# anc-infra

Cloud infrastructure for ANC (Adoración Nocturna Colombiana) on AWS, managed with Terraform and deployed with GitHub Actions.

## Environment and branching

- Single environment: `prod` (`us-east-1`).
- All work happens on `main`. There are no feature branches and no `dev` environment.
- Every push to `main` that touches `infra/**` runs `plan` + `apply` against prod automatically.
- Before pushing, run `terraform fmt -recursive`, `terraform validate` and `terraform plan` from `infra/prod`.

The AWS account is shared with other projects. Every ANC resource uses the `anc-` prefix, and the deploy role can only manage resources with that prefix.

## Layout

- `bootstrap/iam/`: GitHub Actions OIDC deploy role, created manually. See [bootstrap/iam/README.md](bootstrap/iam/README.md).
- `infra/prod/`: Terraform root module for `prod`.
- `infra/scripts/bootstrap-state-bucket.sh`: ensures the remote state bucket exists before `terraform init`.
- `.github/workflows/terraform-plan-apply.yml`: automatic plan/apply on push to `main`; manual `plan` or `apply` via `workflow_dispatch`.

## Required GitHub secrets

| Secret | Description |
| --- | --- |
| `AWS_ACCOUNT_ID` | Target AWS account ID |
| `AWS_DEPLOY_ROLE_ARN` | ARN of the OIDC deploy role |
| `TF_STATE_BUCKET` | S3 bucket holding the Terraform state |
