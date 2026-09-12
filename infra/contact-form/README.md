# Website Contact Form

The public form posts to a dedicated AWS HTTP API. API Gateway applies a low
burst/rate ceiling, Lambda validates bounded input and the browser origin, and
DynamoDB enforces five accepted requests per source IP per hour. A hidden
honeypot absorbs basic form bots. SES sends one message to both:

- `chris.ye@hunchsense.com`
- `shawn.li@hunchsense.com`

The visitor's email is used only as `Reply-To`. No form content is persisted,
and logs contain request/message IDs but not names, email addresses, or message
text. DynamoDB stores only an hourly SHA-256 source-IP bucket and deletes it by
TTL.

## Deploy

Prerequisites are AWS CLI access to the target HunchSense account and a
CloudFormation asset bucket in `us-west-2`.

```bash
AWS_REGION=us-west-2 ./infra/contact-form/deploy.sh
```

The script idempotently creates the SES domain identity and ACM certificate,
adds their validation CNAMEs to the existing Lightsail DNS zone, deploys the
CloudFormation stack, and maps `contact-api.hunchsense.com` to API Gateway.

SES is currently in its sandbox, but the verified `hunchsense.com` domain makes
both recipients valid sandbox destinations. The current 200-message daily SES
quota is sufficient for the rate-limited contact form; request production
access before sending to recipients outside the verified domain.

## Operations

- Stack: `HunchSenseWebsiteContact`
- API: `https://contact-api.hunchsense.com/contact`
- Health: `https://contact-api.hunchsense.com/contact/health`
- Lambda logs: 30-day retention
- API access logs: 14-day retention, with no request body
- DynamoDB: on-demand billing, encrypted, TTL after two hours

Do not put AWS credentials, recipient configuration, or an SES call in the
browser. Recipient addresses and IAM restrictions remain server-side.
