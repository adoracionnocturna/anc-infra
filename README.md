# anc-infra

Cloud infrastructure for ANC (Adoración Nocturna Colombiana) on AWS, managed with Terraform and deployed with GitHub Actions.

## Environment and branching

- Single environment: `prod` (`us-east-1`).
- All work happens on `main`. There are no feature branches and no `dev` environment.
- Every push to `main` that touches `infra/**` or `services/**` runs `plan` + `apply` against prod automatically.
- Before pushing, run `terraform fmt -recursive`, `terraform validate`, `terraform plan` and the service tests.

The AWS account is shared with other projects. Every ANC resource uses the `anc-` prefix, and the deploy role can only manage resources with that prefix.

## Documentation

- [docs/terraform-guidelines.md](docs/terraform-guidelines.md): how Terraform is organized and named, and how to add features and services without over-engineering.
- [docs/decisions.md](docs/decisions.md): decision log.
- [docs/services/README.md](docs/services/README.md): service catalog.

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
