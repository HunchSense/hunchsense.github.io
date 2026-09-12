from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest.mock import Mock


os.environ.update({
    "AWS_DEFAULT_REGION": "us-west-2",
    "AWS_EC2_METADATA_DISABLED": "true",
    "ALLOWED_ORIGINS": "https://hunchsense.com,https://www.hunchsense.com",
    "RATE_LIMIT_TABLE": "contact-rate-limit",
    "RATE_LIMIT_PER_HOUR": "5",
    "SOURCE_EMAIL": "HunchSense Website <website@hunchsense.com>",
    "RECIPIENTS": "chris.ye@hunchsense.com,shawn.li@hunchsense.com",
})

HANDLER_PATH = Path(__file__).parents[1] / "function" / "handler.py"
SPEC = importlib.util.spec_from_file_location("contact_handler", HANDLER_PATH)
assert SPEC and SPEC.loader
handler = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(handler)


def event(payload: dict, *, origin: str = "https://hunchsense.com", method: str = "POST", path: str = "/contact"):
    return {
        "headers": {"origin": origin},
        "body": json.dumps(payload),
        "requestContext": {"http": {"method": method, "path": path, "sourceIp": "203.0.113.10"}},
    }


VALID = {
    "name": "Test Engineer",
    "email": "engineer@example.com",
    "company": "Example Labs",
    "role": "Validation Lab Manager",
    "message": "We need to automate a thermal characterization bench.",
    "website": "",
    "request_id": "123e4567-e89b-42d3-a456-426614174000",
}


class ContactHandlerTests(unittest.TestCase):
    def setUp(self):
        handler.ddb = Mock()
        handler.ddb.update_item.return_value = {"Attributes": {"submissions": {"N": "1"}}}
        handler.ses = Mock()
        handler.ses.send_email.return_value = {"MessageId": "message-123"}

    def test_valid_submission_is_sent_to_both_recipients(self):
        result = handler.handler(event(VALID), None)

        self.assertEqual(result["statusCode"], 202)
        call = handler.ses.send_email.call_args.kwargs
        self.assertEqual(call["Destination"]["ToAddresses"], [
            "chris.ye@hunchsense.com", "shawn.li@hunchsense.com",
        ])
        self.assertEqual(call["ReplyToAddresses"], ["engineer@example.com"])
        self.assertNotIn("engineer@example.com", json.dumps(result))

    def test_invalid_origin_and_payload_are_rejected(self):
        self.assertEqual(handler.handler(event(VALID, origin="https://example.net"), None)["statusCode"], 403)
        invalid = {**VALID, "email": "not-an-email"}
        self.assertEqual(handler.handler(event(invalid), None)["statusCode"], 400)
        handler.ses.send_email.assert_not_called()

    def test_malformed_base64_is_rejected(self):
        invalid_event = event(VALID)
        invalid_event["body"] = "not base64"
        invalid_event["isBase64Encoded"] = True

        result = handler.handler(invalid_event, None)

        self.assertEqual(result["statusCode"], 400)
        handler.ses.send_email.assert_not_called()

    def test_honeypot_is_accepted_without_delivery(self):
        result = handler.handler(event({**VALID, "website": "spam.example"}), None)

        self.assertEqual(result["statusCode"], 202)
        handler.ddb.update_item.assert_not_called()
        handler.ses.send_email.assert_not_called()

    def test_rate_limit_blocks_delivery(self):
        handler.ddb.update_item.return_value = {"Attributes": {"submissions": {"N": "6"}}}

        result = handler.handler(event(VALID), None)

        self.assertEqual(result["statusCode"], 429)
        handler.ses.send_email.assert_not_called()

    def test_delivery_dependency_failure_is_safe(self):
        handler.ddb.update_item.side_effect = handler.BotoCoreError()

        result = handler.handler(event(VALID), None)

        self.assertEqual(result["statusCode"], 503)
        self.assertNotIn(VALID["email"], json.dumps(result))
        handler.ses.send_email.assert_not_called()

    def test_health_does_not_require_an_origin(self):
        result = handler.handler(event({}, origin="", method="GET", path="/contact/health"), None)
        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(json.loads(result["body"]), {"ok": True})


if __name__ == "__main__":
    unittest.main()
