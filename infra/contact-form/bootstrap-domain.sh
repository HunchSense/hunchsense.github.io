#!/usr/bin/env bash
set -euo pipefail

REGION="${AWS_REGION:-us-west-2}"
DNS_REGION="us-east-1"
DOMAIN="hunchsense.com"
API_DOMAIN="contact-api.${DOMAIN}"

for command in aws; do
  command -v "$command" >/dev/null || { echo "$command is required" >&2; exit 1; }
done

upsert_cname() {
  local name="$1" target="$2" existing
  existing="$(aws lightsail get-domain --region "$DNS_REGION" --domain-name "$DOMAIN" \
    --query "domain.domainEntries[?name=='${name}' && type=='CNAME'].target | [0]" --output text)"
  if [[ "$existing" == "$target" ]]; then
    return
  fi
  if [[ "$existing" != "None" && -n "$existing" ]]; then
    aws lightsail update-domain-entry --region "$DNS_REGION" --domain-name "$DOMAIN" \
      --domain-entry "name=${name},type=CNAME,target=${target}" >/dev/null
  else
    aws lightsail create-domain-entry --region "$DNS_REGION" --domain-name "$DOMAIN" \
      --domain-entry "name=${name},type=CNAME,target=${target}" >/dev/null
  fi
}

if ! aws sesv2 get-email-identity --region "$REGION" --email-identity "$DOMAIN" >/dev/null 2>&1; then
  aws sesv2 create-email-identity --region "$REGION" --email-identity "$DOMAIN" >/dev/null
fi

mapfile -t dkim_tokens < <(aws sesv2 get-email-identity --region "$REGION" --email-identity "$DOMAIN" \
  --query 'DkimAttributes.Tokens[]' --output text | tr '\t' '\n')
for token in "${dkim_tokens[@]}"; do
  upsert_cname "${token}._domainkey.${DOMAIN}" "${token}.dkim.amazonses.com"
done

certificate_arn="$(aws acm list-certificates --region "$REGION" \
  --certificate-statuses PENDING_VALIDATION ISSUED \
  --query "CertificateSummaryList[?DomainName=='${API_DOMAIN}'].CertificateArn | [0]" --output text)"
if [[ "$certificate_arn" == "None" || -z "$certificate_arn" ]]; then
  certificate_arn="$(aws acm request-certificate --region "$REGION" \
    --domain-name "$API_DOMAIN" --validation-method DNS \
    --idempotency-token hunchsensecontact --query CertificateArn --output text)"
fi

validation_name=""
for _ in $(seq 1 20); do
  validation_name="$(aws acm describe-certificate --region "$REGION" --certificate-arn "$certificate_arn" \
    --query 'Certificate.DomainValidationOptions[0].ResourceRecord.Name' --output text)"
  [[ "$validation_name" != "None" && -n "$validation_name" ]] && break
  sleep 2
done
validation_target="$(aws acm describe-certificate --region "$REGION" --certificate-arn "$certificate_arn" \
  --query 'Certificate.DomainValidationOptions[0].ResourceRecord.Value' --output text)"
upsert_cname "${validation_name%.}" "${validation_target%.}"

for _ in $(seq 1 120); do
  certificate_status="$(aws acm describe-certificate --region "$REGION" --certificate-arn "$certificate_arn" \
    --query 'Certificate.Status' --output text)"
  [[ "$certificate_status" == "ISSUED" ]] && break
  sleep 5
done
[[ "${certificate_status:-}" == "ISSUED" ]] || { echo "Certificate validation timed out" >&2; exit 1; }

echo "$certificate_arn"
