# anc-infra

AWS infrastructure for ANC, managed with Terraform and deployed by GitHub Actions on push to `main`.

Read before changing anything:

- [docs/terraform-guidelines.md](docs/terraform-guidelines.md): layout, naming, when to create modules, public-repo rules.
- [docs/decisions.md](docs/decisions.md): why things are the way they are.
- [docs/services/README.md](docs/services/README.md): what is deployed.
- [docs/api/README.md](docs/api/README.md) and [docs/api/openapi.yaml](docs/api/openapi.yaml): API contract for clients; update them with every route change.

Key rules:

- Keep it simple: building-block modules + one `infra/prod/<service>.tf` per service. No per-service modules, no third-party modules, no workspaces.
- Features are configuration inside a service whenever possible.
- This repository is public: English only; never commit account IDs, profile names, tokens or personal data; do not output identifiers from Terraform.
- Every AWS resource name starts with `anc-` (secrets: `anc/`).
- Update `docs/` in the same commit as the change it describes.
- Before pushing: `terraform fmt -recursive`, `terraform validate`, `terraform plan`, and service tests.
