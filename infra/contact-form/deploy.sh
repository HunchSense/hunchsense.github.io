#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REGION="${AWS_REGION:-us-west-2}"
DNS_REGION="us-east-1"
STACK_NAME="${CONTACT_STACK_NAME:-HunchSenseWebsiteContact}"
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
ASSET_BUCKET="${CONTACT_ASSET_BUCKET:-cdk-hnb659fds-assets-${ACCOUNT_ID}-${REGION}}"
PACKAGED_TEMPLATE="$(mktemp)"
trap 'unlink "$PACKAGED_TEMPLATE" 2>/dev/null || true' EXIT

certificate_arn="$(${ROOT}/infra/contact-form/bootstrap-domain.sh)"
aws cloudformation package --region "$REGION" \
  --template-file "$ROOT/infra/contact-form/template.yaml" \
  --s3-bucket "$ASSET_BUCKET" \
  --s3-prefix hunchsense-website/contact-form \
  --output-template-file "$PACKAGED_TEMPLATE" >/dev/null
aws cloudformation deploy --region "$REGION" \
  --stack-name "$STACK_NAME" \
  --template-file "$PACKAGED_TEMPLATE" \
  --parameter-overrides "CertificateArn=${certificate_arn}" \
  --capabilities CAPABILITY_IAM \
  --tags Application=HunchSenseWebsite ManagedBy=CloudFormation

regional_target="$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='RegionalDomainName'].OutputValue" --output text)"
existing="$(aws lightsail get-domain --region "$DNS_REGION" --domain-name hunchsense.com \
  --query "domain.domainEntries[?name=='contact-api.hunchsense.com' && type=='CNAME'].target | [0]" --output text)"
if [[ "$existing" != "$regional_target" ]]; then
  if [[ "$existing" != "None" && -n "$existing" ]]; then
    aws lightsail update-domain-entry --region "$DNS_REGION" --domain-name hunchsense.com \
      --domain-entry "name=contact-api.hunchsense.com,type=CNAME,target=${regional_target}" >/dev/null
  else
    aws lightsail create-domain-entry --region "$DNS_REGION" --domain-name hunchsense.com \
      --domain-entry "name=contact-api.hunchsense.com,type=CNAME,target=${regional_target}" >/dev/null
  fi
fi

echo "Contact API deployed: https://contact-api.hunchsense.com/contact"
