from __future__ import annotations

import base64
import binascii
from datetime import datetime, timezone
import hashlib
import html
import json
import os
import re
import time
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError


ddb = boto3.client("dynamodb")
ses = boto3.client("sesv2")

ALLOWED_ORIGINS = frozenset(filter(None, os.environ["ALLOWED_ORIGINS"].split(",")))
RATE_LIMIT_TABLE = os.environ["RATE_LIMIT_TABLE"]
RATE_LIMIT_PER_HOUR = int(os.environ.get("RATE_LIMIT_PER_HOUR", "5"))
SOURCE_EMAIL = os.environ["SOURCE_EMAIL"]
RECIPIENTS = tuple(filter(None, os.environ["RECIPIENTS"].split(",")))
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
REQUEST_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.I)


class RequestError(ValueError):
    pass


def response(status: int, payload: dict[str, Any], origin: str | None = None) -> dict[str, Any]:
    headers = {
        "content-type": "application/json; charset=utf-8",
        "cache-control": "no-store",
        "x-content-type-options": "nosniff",
    }
    if origin in ALLOWED_ORIGINS:
        headers["access-control-allow-origin"] = origin
        headers["vary"] = "origin"
    return {"statusCode": status, "headers": headers, "body": json.dumps(payload)}


def field(payload: dict[str, Any], name: str, limit: int, *, required: bool = True, multiline: bool = False) -> str:
    value = payload.get(name, "")
    if not isinstance(value, str):
        raise RequestError(f"{name} must be text")
    value = value.strip()
    if required and not value:
        raise RequestError(f"{name} is required")
    if len(value) > limit:
        raise RequestError(f"{name} is too long")
    if not multiline and any(character in value for character in "\r\n"):
        raise RequestError(f"{name} must be a single line")
    return value


def parse_payload(event: dict[str, Any]) -> dict[str, Any]:
    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        try:
            body = base64.b64decode(body, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeError, ValueError) as exc:
            raise RequestError("request must be valid base64-encoded UTF-8") from exc
    if not isinstance(body, str) or len(body.encode("utf-8")) > 12_000:
        raise RequestError("request is too large")
    try:
        payload = json.loads(body)
    except (TypeError, ValueError, UnicodeError) as exc:
        raise RequestError("request must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise RequestError("request must be a JSON object")
    return payload


def allow_submission(source_ip: str) -> bool:
    now = int(time.time())
    bucket = now // 3600
    key = hashlib.sha256(f"{bucket}:{source_ip}".encode()).hexdigest()
    result = ddb.update_item(
        TableName=RATE_LIMIT_TABLE,
        Key={"bucket_key": {"S": key}},
        UpdateExpression="SET expires_at = if_not_exists(expires_at, :expires) ADD submissions :one",
        ExpressionAttributeValues={
            ":expires": {"N": str(now + 7200)},
            ":one": {"N": "1"},
        },
        ReturnValues="UPDATED_NEW",
    )
    count = int(result["Attributes"]["submissions"]["N"])
    return count <= RATE_LIMIT_PER_HOUR


def send_message(values: dict[str, str], request_id: str) -> str:
    received = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    labels = (("Name", "name"), ("Email", "email"), ("Company", "company"), ("Role", "role"))
    plain = ["New HunchSense website inquiry", ""]
    plain.extend(f"{label}: {values[key]}" for label, key in labels)
    plain.extend(("", "Message:", values["message"], "", f"Received: {received}", f"Request ID: {request_id or '-'}"))
    escaped_message = html.escape(values["message"]).replace("\n", "<br>")
    rows = "".join(
        f"<tr><th align='left'>{label}</th><td>{html.escape(values[key])}</td></tr>"
        for label, key in labels
    )
    markup = (
        "<h2>New HunchSense website inquiry</h2>"
        f"<table cellpadding='6'>{rows}</table>"
        f"<h3>Message</h3><p>{escaped_message}</p>"
        f"<p><small>Received {received} | Request ID {html.escape(request_id or '-')}</small></p>"
    )
    subject_company = values["company"].replace("\r", " ").replace("\n", " ")[:70]
    result = ses.send_email(
        FromEmailAddress=SOURCE_EMAIL,
        Destination={"ToAddresses": list(RECIPIENTS)},
        ReplyToAddresses=[values["email"]],
        Content={"Simple": {
            "Subject": {"Data": f"[HunchSense website] {subject_company}", "Charset": "UTF-8"},
            "Body": {
                "Text": {"Data": "\n".join(plain), "Charset": "UTF-8"},
                "Html": {"Data": markup, "Charset": "UTF-8"},
            },
        }},
    )
    return result["MessageId"]


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    del context
    request_context = event.get("requestContext") or {}
    http = request_context.get("http") or {}
    method = str(http.get("method") or "").upper()
    path = str(http.get("path") or event.get("rawPath") or "")
    headers = {str(key).lower(): str(value) for key, value in (event.get("headers") or {}).items()}
    origin = headers.get("origin")

    if method == "GET" and path.endswith("/health"):
        return response(200, {"ok": True})
    if method != "POST":
        return response(405, {"message": "Method not allowed."}, origin)
    if origin not in ALLOWED_ORIGINS:
        return response(403, {"message": "Request origin is not allowed."})

    try:
        payload = parse_payload(event)
        if field(payload, "website", 200, required=False):
            return response(202, {"accepted": True}, origin)
        values = {
            "name": field(payload, "name", 100),
            "email": field(payload, "email", 254).lower(),
            "company": field(payload, "company", 120),
            "role": field(payload, "role", 100),
            "message": field(payload, "message", 2000, multiline=True),
        }
        if not EMAIL_RE.fullmatch(values["email"]):
            raise RequestError("email is invalid")
        request_id = field(payload, "request_id", 36, required=False)
        if request_id and not REQUEST_ID_RE.fullmatch(request_id):
            raise RequestError("request_id is invalid")
    except RequestError as exc:
        return response(400, {"message": str(exc)}, origin)

    try:
        source_ip = str(http.get("sourceIp") or "unknown")
        if not allow_submission(source_ip):
            return response(429, {"message": "Too many requests. Please try again later."}, origin)
        message_id = send_message(values, request_id)
        print(json.dumps({"event": "contact_delivered", "message_id": message_id, "request_id": request_id}))
    except (BotoCoreError, ClientError) as exc:
        code = (
            exc.response.get("Error", {}).get("Code", "ClientError")
            if isinstance(exc, ClientError)
            else type(exc).__name__
        )
        print(json.dumps({"event": "contact_delivery_failed", "code": code, "request_id": request_id}))
        return response(503, {"message": "Delivery is temporarily unavailable. Please email our team directly."}, origin)
    return response(202, {"accepted": True}, origin)
