# GitHub Actions deploy role (manual bootstrap)

This role is created manually, once, outside Terraform, because Terraform needs it in order to run.

- Role name: `GitHubActionsAncDeployRole`
- Trust: only `adoracionnocturna/anc-infra`, branch `main`, through GitHub OIDC ([trust-policy.json](trust-policy.json))
- Permissions: inline policy `anc-terraform-deploy`, limited to `anc-*` resources ([deploy-policy.json](deploy-policy.json))

The AWS account is shared with other projects. Do not modify their roles; this role is exclusive to ANC.

The policy files use the `<AWS_ACCOUNT_ID>` placeholder. Never commit the real account ID.

## OIDC subject

The repository uses GitHub's immutable subject claim, so `sub` includes the owner and repository IDs:

```
repo:adoracionnocturna@349460235/anc-infra@1437422478:ref:refs/heads/main
```

Check it with:

```bash
gh api repos/adoracionnocturna/anc-infra/actions/oidc/customization/sub
```

## Create / update

From the repository root, with AWS credentials that can manage IAM:

```bash
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
mkdir -p /tmp/anc-iam
for f in trust-policy deploy-policy; do
  sed "s/<AWS_ACCOUNT_ID>/${AWS_ACCOUNT_ID}/g" "bootstrap/iam/${f}.json" > "/tmp/anc-iam/${f}.json"
done

aws iam create-role \
  --role-name GitHubActionsAncDeployRole \
  --assume-role-policy-document file:///tmp/anc-iam/trust-policy.json \
  --description "GitHub Actions deploy role for adoracionnocturna/anc-infra" \
  --tags Key=Project,Value=anc Key=ManagedBy,Value=manual

aws iam put-role-policy \
  --role-name GitHubActionsAncDeployRole \
  --policy-name anc-terraform-deploy \
  --policy-document file:///tmp/anc-iam/deploy-policy.json
```

To apply later changes, use `aws iam update-assume-role-policy` (trust) or run `put-role-policy` again (permissions).
