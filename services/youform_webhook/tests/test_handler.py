import base64
import hashlib
import hmac
import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import handler  # noqa: E402

PARTICIPANT_FORM = "form0001"
LEADER_FORM = "form0002"
SECRETS = {PARTICIPANT_FORM: "participant-secret", LEADER_FORM: "leader-secret"}


class FakeS3:
    def __init__(self, fail: bool = False):
        self.objects: dict[str, bytes] = {}
        self.fail = fail

    def put_object(self, Bucket, Key, Body, ContentType):
        if self.fail:
            raise RuntimeError("s3 down")
        self.objects[f"{Bucket}/{Key}"] = Body


class FakeTable:
    def __init__(self):
        self.items: list[dict] = []

    def put_item(self, Item):
        self.items.append(Item)


def payload(form_id: str, submission_id: str = "sub123") -> dict:
    return {
        "event_id": "evt-1",
        "event_type": "submission",
        "form_id": form_id,
        "form_name": "Test form",
        "submission_id": submission_id,
        "started_at": "2026-11-02T14:30:02.000000Z",
        "completed_at": "2026-11-02T15:32:33.000000Z",
        "fields": [
            {"id": "q1", "question": "Name", "position": 1, "type": "short_text", "answer": "Ana"},
            {"id": "q2", "question": "Rating", "position": 2, "type": "rating", "answer": "5"},
            {"id": "q3", "question": "Comments", "position": 3, "type": "long_text", "answer": ""},
            {"question": "Field without id", "answer": "ignored"},
        ],
    }


def event(body: dict | str, secret: str | None = None, base64_encoded: bool = False, signature: str | None = None) -> dict:
    raw = body if isinstance(body, str) else json.dumps(body)
    headers = {}
    if signature is not None:
        headers["signature"] = signature
    elif secret is not None:
        headers["signature"] = hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()
    return {
        "headers": headers,
        "body": base64.b64encode(raw.encode()).decode() if base64_encoded else raw,
        "isBase64Encoded": base64_encoded,
    }


class HandlerTest(unittest.TestCase):
    def setUp(self):
        os.environ["FORMS_CONFIG"] = json.dumps(
            {
                PARTICIPANT_FORM: {"slug": "participant-feedback", "store_in_dynamodb": True},
                LEADER_FORM: {"slug": "leader-self-assessment", "store_in_dynamodb": False},
            }
        )
        os.environ["SECRET_ID"] = "anc/prod/youform-intake"
        os.environ["SUBMISSIONS_BUCKET"] = "bucket"
        os.environ["RESPONSES_TABLE"] = "table"
        self.s3 = FakeS3()
        self.table = FakeTable()
        handler._signing_secrets = dict(SECRETS)
        handler._clients.clear()
        handler._clients.update({"s3": self.s3, "responses_table": self.table})

    def invoke(self, evt: dict) -> tuple[int, dict]:
        result = handler.handler(evt, None)
        return result["statusCode"], json.loads(result["body"])

    def test_participant_feedback_goes_to_s3_and_dynamodb(self):
        body = payload(PARTICIPANT_FORM)
        status, response = self.invoke(event(body, SECRETS[PARTICIPANT_FORM]))

        self.assertEqual(status, 200)
        self.assertTrue(response["ok"])
        key = "bucket/submissions/participant-feedback/2026/11/sub123.json"
        self.assertEqual(json.loads(self.s3.objects[key]), body)
        self.assertEqual(len(self.table.items), 1)
        item = self.table.items[0]
        self.assertEqual(item["pk"], "FORM#form0001")
        self.assertEqual(item["sk"], "SUBMISSION#sub123")
        self.assertEqual(item["raw_s3_key"], "submissions/participant-feedback/2026/11/sub123.json")
        self.assertEqual(
            item["answers"],
            {
                "q1": {"question": "Name", "position": 1, "type": "short_text", "answer": "Ana"},
                "q2": {"question": "Rating", "position": 2, "type": "rating", "answer": "5"},
                "q3": {"question": "Comments", "position": 3, "type": "long_text"},
            },
        )

    def test_leader_self_assessment_goes_only_to_s3(self):
        status, _ = self.invoke(event(payload(LEADER_FORM), SECRETS[LEADER_FORM]))

        self.assertEqual(status, 200)
        self.assertIn("bucket/submissions/leader-self-assessment/2026/11/sub123.json", self.s3.objects)
        self.assertEqual(self.table.items, [])

    def test_raw_body_is_stored_byte_for_byte(self):
        raw = '{"form_id": "form0002", "submission_id": "abc", "completed_at": "2026-11-02T15:32:33Z", "fields": []}'
        status, _ = self.invoke(event(raw, SECRETS[LEADER_FORM]))

        self.assertEqual(status, 200)
        self.assertEqual(self.s3.objects["bucket/submissions/leader-self-assessment/2026/11/abc.json"], raw.encode())

    def test_base64_encoded_body(self):
        status, _ = self.invoke(event(payload(LEADER_FORM), SECRETS[LEADER_FORM], base64_encoded=True))
        self.assertEqual(status, 200)

    def test_signature_header_is_case_insensitive(self):
        evt = event(payload(LEADER_FORM), SECRETS[LEADER_FORM])
        evt["headers"] = {"Signature": evt["headers"]["signature"]}
        status, _ = self.invoke(evt)
        self.assertEqual(status, 200)

    def test_invalid_signature_is_rejected_without_storing(self):
        status, response = self.invoke(event(payload(PARTICIPANT_FORM), signature="deadbeef"))

        self.assertEqual(status, 401)
        self.assertEqual(response["error"], "unauthorized")
        self.assertEqual(self.s3.objects, {})
        self.assertEqual(self.table.items, [])

    def test_signature_from_another_form_is_rejected(self):
        status, _ = self.invoke(event(payload(PARTICIPANT_FORM), SECRETS[LEADER_FORM]))
        self.assertEqual(status, 401)

    def test_missing_signature_is_rejected(self):
        status, _ = self.invoke(event(payload(PARTICIPANT_FORM)))
        self.assertEqual(status, 401)

    def test_unknown_form_is_rejected(self):
        status, _ = self.invoke(event(payload("unknown1"), "whatever"))
        self.assertEqual(status, 401)
        self.assertEqual(self.s3.objects, {})

    def test_missing_secret_returns_500_so_youform_retries(self):
        handler._signing_secrets = {LEADER_FORM: SECRETS[LEADER_FORM]}
        status, response = self.invoke(event(payload(PARTICIPANT_FORM), SECRETS[PARTICIPANT_FORM]))
        self.assertEqual(status, 500)
        self.assertEqual(response["error"], "configuration_error")

    def test_invalid_json_is_rejected(self):
        status, _ = self.invoke(event("not json", SECRETS[LEADER_FORM]))
        self.assertEqual(status, 400)

    def test_non_object_json_is_rejected(self):
        status, _ = self.invoke(event("[1, 2]", SECRETS[LEADER_FORM]))
        self.assertEqual(status, 400)

    def test_unsafe_submission_id_is_rejected(self):
        status, response = self.invoke(event(payload(LEADER_FORM, "../../etc"), SECRETS[LEADER_FORM]))
        self.assertEqual(status, 400)
        self.assertEqual(response["error"], "invalid_submission_id")
        self.assertEqual(self.s3.objects, {})

    def test_storage_failure_returns_500_so_youform_retries(self):
        handler._clients["s3"] = FakeS3(fail=True)
        status, response = self.invoke(event(payload(PARTICIPANT_FORM), SECRETS[PARTICIPANT_FORM]))
        self.assertEqual(status, 500)
        self.assertEqual(response["error"], "storage_error")
        self.assertEqual(self.table.items, [])

    def test_missing_completed_at_uses_received_date(self):
        body = payload(LEADER_FORM)
        del body["completed_at"]
        status, _ = self.invoke(event(body, SECRETS[LEADER_FORM]))
        self.assertEqual(status, 200)
        (key,) = self.s3.objects
        self.assertRegex(key, r"^bucket/submissions/leader-self-assessment/\d{4}/\d{2}/sub123\.json$")


if __name__ == "__main__":
    unittest.main()
