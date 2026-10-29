# Terraform guidelines

How infrastructure in this repository is organized, named and grown. The goal is to support many future services and features while keeping the code **flat, explicit and boring**.

When in doubt, choose the option with fewer files, fewer variables and fewer layers.

## 1. Layout

```
anc-infra/
├── bootstrap/iam/            # Manual, one-time resources Terraform depends on (deploy role)
├── infra/
│   ├── prod/                 # Root module: composition only
│   │   ├── backend.tf  versions.tf  providers.tf  variables.tf
│   │   ├── locals.tf         # Shared naming, tags, region
│   │   ├── <service>.tf      # One file per service
│   │   └── outputs.tf
│   ├── modules/              # Generic building blocks (no business logic)
│   │   └── <block>/          # main.tf, variables.tf, outputs.tf
│   └── scripts/              # Bootstrap helpers used by CI
├── services/                 # Lambda source code, one folder per function
│   └── <function_name>/
│       ├── handler.py
│       └── tests/
└── docs/                     # This guide, decision log, service catalog
```

## 2. Two layers, never three

| Layer | Location | Knows about | Example |
| --- | --- | --- | --- |
| Building blocks | `infra/modules/<block>/` | One AWS pattern with secure defaults | `lambda-function`, `http-api`, `s3-private-bucket` |
| Services | `infra/prod/<service>.tf` | The business capability | `youform-intake.tf` |

- A **service file** composes building blocks and adds service-specific resources directly: DynamoDB tables, least-privilege IAM policies, secrets.
- Do **not** create per-service modules (e.g. `modules/youform-intake`). They force long lists of pass-through variables and hide what a service actually creates.
- Modules never call other modules.

### When to create a building block

Create a module only when **all** of these are true:

1. It groups two or more resources that always go together (e.g. bucket + versioning + encryption + public access block).
2. It enforces defaults we want everywhere (encryption, log retention, blocked public access).
3. It is used, or clearly about to be used, by more than one service.

A single resource (e.g. one DynamoDB table) goes straight into the service file. Copying a block of HCL once is fine; extract it the second or third time.

### Module rules

- Files: `main.tf`, `variables.tf`, `outputs.tf`. Nothing else unless needed.
- Every variable has `type` and `description`. Prefer few variables with sensible defaults.
- The main resource is named `this`.
- No provider blocks inside modules; no hardcoded names, account IDs or regions.
- No third-party registry modules. Our modules stay short enough to read in one sitting.

## 3. Services vs. features

- **Service**: a business capability with its own entry point and data. Gets its own `infra/prod/<service>.tf`, its own code under `services/`, and a section in [services/README.md](services/README.md).
- **Feature**: something that grows *inside* a service. It should be configuration or code, not new infrastructure, whenever possible.

Example: every YouForm form shares one webhook, one function, one bucket and one table. A new form is a new entry in a map, which also acts as the allowlist:

```hcl
locals {
  youform_forms = {
    ajbsvmgt = "participant-feedback"
    txrpjpz3 = "leader-self-assessment"
  }
}
```

| You are adding | You change |
| --- | --- |
| A new form / variant of existing input | A config entry (map in `locals`) |
| New behavior in an existing service | That service's `.tf` file and its code in `services/` |
| A new business capability | New `infra/prod/<service>.tf`, new `services/<function>/`, catalog entry |
| A pattern repeated by 2+ services | Consider a building block in `infra/modules/` |

New infrastructure for a feature (another table, queue, function) needs a reason written in [decisions.md](decisions.md).

## 4. Naming

| Item | Convention | Example |
| --- | --- | --- |
| Name prefix | `local.name_prefix` = `anc-<env>` | `anc-prod` |
| AWS resources | `<prefix>-<service>-<component>` | `anc-prod-youform-webhook` |
| S3 buckets (global) | `<prefix>-<service>-<component>-<account_id>-<region>` | `anc-prod-youform-responses-<account_id>-us-east-1` |
| DynamoDB tables | `<prefix>-<service>-<entity>` | `anc-prod-youform-responses` |
| Secrets Manager | `anc/<env>/<service>` | `anc/prod/youform-intake` |
| IAM roles (workloads) | `<prefix>-<service>-<component>-role` | `anc-prod-youform-webhook-role` |
| `.tf` files, module folders | kebab-case | `youform-intake.tf`, `s3-private-bucket/` |
| Terraform identifiers, variables, outputs | snake_case | `module.youform_webhook` |
| Lambda code folders | snake_case | `services/youform_webhook/` |

- Every AWS resource name starts with `anc-` (or `anc/` for secrets). The deploy role can only manage resources with that prefix.
- Tags: `default_tags` in the provider set `ManagedBy`, `Environment`, `Project`, `Repository`. Each service adds `Service = "<service>"`.

## 5. Public repository rules

This repository is public.

- Everything is written in English: code, comments, docs, workflow text.
- Never commit the AWS account ID, local profile names, credentials, tokens or personal data. Use `data.aws_caller_identity` in Terraform and GitHub secrets in CI.
- Do not output identifiers (account ID, ARNs) from Terraform; Actions logs are public.
- Runtime secrets (e.g. webhook tokens) live in AWS Secrets Manager, never in GitHub or in the repo.
- `.env` is git-ignored; `.env.example` lists the keys without values.

## 6. Lambda code and packaging

- Python, stdlib + `boto3` (already in the runtime) by default.
- Packaged by Terraform with the `archive_file` data source from `services/<function>/`. No per-function build scripts.
- If a function needs third-party dependencies, add a build step for that function only and record why in [decisions.md](decisions.md).
- Each function has unit tests in `services/<function>/tests/` that run without AWS.

## 7. Environment and delivery

- Single environment: `prod`. Single branch: `main`.
- Push to `main` touching `infra/**` or `services/**` runs `plan` + `apply` automatically.
- Before pushing: `terraform fmt -recursive`, `terraform validate`, `terraform plan` and the service tests.
- No workspaces, no Terragrunt, no per-environment tfvars until a second environment actually exists.

## 8. Documentation as you go

Documentation changes ship in the **same commit** as the change they describe:

- New or changed service: update [services/README.md](services/README.md) (what it does, entry point, resources, data layout).
- Decision that affects structure, security or cost (new building block, new dependency, new resource type, exception to this guide): add an entry to [decisions.md](decisions.md).
- Change to these rules: edit this guide and add a decision entry explaining why.
