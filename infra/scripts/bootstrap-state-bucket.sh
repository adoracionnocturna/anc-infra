#!/usr/bin/env bash

set -euo pipefail

AWS_REGION="us-east-1"
STATE_BUCKET_NAME="${TF_STATE_BUCKET:?TF_STATE_BUCKET must be set}"

echo "Ensuring Terraform state bucket exists."

if aws s3api head-bucket --bucket "${STATE_BUCKET_NAME}" --region "${AWS_REGION}" 2>/dev/null; then
  echo "State bucket already exists."
else
  echo "Creating state bucket in ${AWS_REGION}."
  aws s3api create-bucket \
    --bucket "${STATE_BUCKET_NAME}" \
    --region "${AWS_REGION}" >/dev/null
fi

aws s3api put-bucket-versioning \
  --bucket "${STATE_BUCKET_NAME}" \
  --region "${AWS_REGION}" \
  --versioning-configuration Status=Enabled

aws s3api put-bucket-encryption \
  --bucket "${STATE_BUCKET_NAME}" \
  --region "${AWS_REGION}" \
  --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

aws s3api put-public-access-block \
  --bucket "${STATE_BUCKET_NAME}" \
  --region "${AWS_REGION}" \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

aws s3api put-bucket-tagging \
  --bucket "${STATE_BUCKET_NAME}" \
  --region "${AWS_REGION}" \
  --tagging 'TagSet=[{Key=Project,Value=anc},{Key=Purpose,Value=terraform-state},{Key=ManagedBy,Value=bootstrap-script}]'

echo "Terraform state bucket is ready."
