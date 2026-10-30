import base64
import json
import os
import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import handler  # noqa: E402

FORM_ID = "form0001"
READER_GROUP = "insights-readers"


class FakeTable:
    """In-memory stand-in for the DynamoDB table: query by pk (sorted by sk) and get_item."""

    def __init__(self, items: list[dict]):
        self.items = sorted(items, key=lambda item: (item["pk"], item["sk"]))
        self.queries: list[dict] = []

    def query(self, KeyConditionExpression, ExpressionAttributeValues, Limit=None, ExclusiveStartKey=None, Select=None):
        self.queries.append({"Limit": Limit, "ExclusiveStartKey": ExclusiveStartKey, "Select": Select})
        matches = [item for item in self.items if item["pk"] == ExpressionAttributeValues[":pk"]]
        if ExclusiveStartKey:
            matches = [item for item in matches if item["sk"] > ExclusiveStartKey["sk"]]
        page = matches[:Limit] if Limit else matches
        result = {"Count": len(page)} if Select == "COUNT" else {"Items": page, "Count": len(page)}
        if Limit and len(matches) > Limit:
            result["LastEvaluatedKey"] = {"pk": page[-1]["pk"], "sk": page[-1]["sk"]}
        return result

    def get_item(self, Key):
        for item in self.items:
            if item["pk"] == Key["pk"] and item["sk"] == Key["sk"]:
                return {"Item": item}
        return {}


def stored_item(submission_id: str, form_id: str = FORM_ID) -> dict:
    return {
        "pk": f"FORM#{form_id}",
        "sk": f"SUBMISSION#{submission_id}",
        "form_id": form_id,
        "form_slug": "participant-feedback",
        "form_name": "Test form",
        "submission_id": submission_id,
        "started_at": "2026-11-02T09:30:02-05:00",
        "completed_at": "2026-11-02T10:32:33-05:00",
        "received_at": "2026-11-02T10:32:34-05:00",
        "raw_s3_key": f"submissions/participant-feedback/2026/11/{submission_id}.json",
        # As stored by youform_webhook: YouForm sends every answer as a string.
        "answers": {
            "q2": {"question": "Recommend", "position": Decimal("2"), "type": "nps", "answer": "9"},
            "q1": {"question": "Age", "position": Decimal("1"), "type": "radio", "answer": "18-24"},
            "q3": {"question": "Topics", "position": Decimal("3"), "type": "checkbox", "answer": "A, B and C"},
            "q4": {"question": "Pace", "position": Decimal("4"), "type": "opinion_scale", "answer": "6.5"},
            "q5": {"question": "Comments", "position": Decimal("5"), "type": "textarea"},
        },
    }


def event(route: str, path: dict | None = None, query: dict | None = None, groups=f"[{READER_GROUP}]") -> dict:
    claims = {"sub": "user-1"}
    if groups is not None:
        claims["cognito:groups"] = groups
    return {
        "routeKey": route,
        "pathParameters": path,
        "queryStringParameters": query,
        "requestContext": {"authorizer": {"jwt": {"claims": claims}}},
    }


class HandlerTest(unittest.TestCase):
    def setUp(self):
        os.environ["FORMS_CONFIG"] = json.dumps({"participant-feedback": FORM_ID})
        os.environ["RESPONSES_TABLE"] = "table"
        os.environ["READER_GROUP"] = READER_GROUP
        self.table = FakeTable(
            [stored_item(f"sub{i}") for i in range(5)] + [stored_item("other", form_id="form0002")]
        )
        handler._clients.clear()
        handler._clients["responses_table"] = self.table

    def invoke(self, evt: dict) -> tuple[int, dict, dict]:
        result = handler.handler(evt, None)
        return result["statusCode"], json.loads(result["body"]), result["headers"]

    def test_list_forms_counts_submissions(self):
        status, body, _ = self.invoke(event("GET /insights/forms"))

        self.assertEqual(status, 200)
        self.assertEqual(body, {"items": [{"form": "participant-feedback", "submission_count": 5}]})

    def test_list_submissions_returns_clean_records(self):
        status, body, headers = self.invoke(
            event("GET /insights/forms/{form}/submissions", {"form": "participant-feedback"})
        )

        self.assertEqual(status, 200)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(len(body["items"]), 5)
        self.assertIsNone(body["next_cursor"])
        first = body["items"][0]
        self.assertEqual(
            first,
            {
                "form": "participant-feedback",
                "submission_id": "sub0",
                "form_name": "Test form",
                "started_at": "2026-11-02T09:30:02-05:00",
                "completed_at": "2026-11-02T10:32:33-05:00",
                "received_at": "2026-11-02T10:32:34-05:00",
                "answers": [
                    {"field_id": "q1", "position": 1, "type": "radio", "question": "Age", "answer": "18-24"},
                    {"field_id": "q2", "position": 2, "type": "nps", "question": "Recommend", "answer": 9},
                    {"field_id": "q3", "position": 3, "type": "checkbox", "question": "Topics", "answer": ["A", "B and C"]},
                    {"field_id": "q4", "position": 4, "type": "opinion_scale", "question": "Pace", "answer": 6.5},
                    {"field_id": "q5", "position": 5, "type": "textarea", "question": "Comments"},
                ],
            },
        )

    def test_non_numeric_value_of_numeric_type_is_kept_as_text(self):
        for value in ("n/a", "NaN", "Infinity"):
            self.table.items[0]["answers"]["q2"]["answer"] = value
            _, body, _ = self.invoke(event("GET /insights/forms/{form}/submissions", {"form": "participant-feedback"}))
            self.assertEqual(body["items"][0]["answers"][1]["answer"], value)

    def test_pagination_with_cursor(self):
        route = "GET /insights/forms/{form}/submissions"
        path = {"form": "participant-feedback"}

        _, page1, _ = self.invoke(event(route, path, {"limit": "2"}))
        _, page2, _ = self.invoke(event(route, path, {"limit": "2", "cursor": page1["next_cursor"]}))
        _, page3, _ = self.invoke(event(route, path, {"limit": "2", "cursor": page2["next_cursor"]}))

        ids = [item["submission_id"] for page in (page1, page2, page3) for item in page["items"]]
        self.assertEqual(ids, ["sub0", "sub1", "sub2", "sub3", "sub4"])
        self.assertIsNone(page3["next_cursor"])

    def test_cursor_cannot_reach_another_form(self):
        cursor = base64.urlsafe_b64encode(json.dumps({"sk": "SUBMISSION#sub3"}).encode()).decode()
        self.invoke(event("GET /insights/forms/{form}/submissions", {"form": "participant-feedback"}, {"cursor": cursor}))
        self.assertEqual(self.table.queries[-1]["ExclusiveStartKey"], {"pk": f"FORM#{FORM_ID}", "sk": "SUBMISSION#sub3"})

    def test_invalid_cursor_is_rejected(self):
        route = "GET /insights/forms/{form}/submissions"
        for cursor in ("not-base64!", base64.urlsafe_b64encode(b'{"sk": "OTHER#x"}').decode()):
            status, body, _ = self.invoke(event(route, {"form": "participant-feedback"}, {"cursor": cursor}))
            self.assertEqual(status, 400)
            self.assertEqual(body["error"], "invalid_parameter")

    def test_invalid_limit_is_rejected(self):
        for limit in ("0", "101", "abc", "-1"):
            status, _, _ = self.invoke(
                event("GET /insights/forms/{form}/submissions", {"form": "participant-feedback"}, {"limit": limit})
            )
            self.assertEqual(status, 400)

    def test_get_submission(self):
        status, body, _ = self.invoke(
            event(
                "GET /insights/forms/{form}/submissions/{submission_id}",
                {"form": "participant-feedback", "submission_id": "sub3"},
            )
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["submission_id"], "sub3")
        self.assertNotIn("raw_s3_key", body)

    def test_unknown_submission_is_404(self):
        route = "GET /insights/forms/{form}/submissions/{submission_id}"
        for submission_id in ("missing", "../etc"):
            status, body, _ = self.invoke(event(route, {"form": "participant-feedback", "submission_id": submission_id}))
            self.assertEqual(status, 404)
            self.assertEqual(body["error"], "not_found")

    def test_forms_not_in_config_are_not_readable(self):
        # Leader self-assessment is S3-only and must not be readable, even by slug.
        status, _, _ = self.invoke(
            event("GET /insights/forms/{form}/submissions", {"form": "leader-self-assessment"})
        )
        self.assertEqual(status, 404)

    def test_user_outside_reader_group_is_forbidden(self):
        for groups in (None, "[]", "[other-group]"):
            status, body, _ = self.invoke(event("GET /insights/forms", groups=groups))
            self.assertEqual(status, 403)
            self.assertEqual(body["error"], "forbidden")
        self.assertEqual(self.table.queries, [])

    def test_groups_claim_as_list_is_accepted(self):
        status, _, _ = self.invoke(event("GET /insights/forms", groups=["other", READER_GROUP]))
        self.assertEqual(status, 200)

    def test_storage_failure_returns_500(self):
        def fail(**_kwargs):
            raise RuntimeError("dynamodb down")

        self.table.query = fail
        status, body, _ = self.invoke(event("GET /insights/forms"))
        self.assertEqual(status, 500)
        self.assertEqual(body["error"], "internal_error")

    def test_unknown_route_is_404(self):
        status, _, _ = self.invoke(event("GET /other"))
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
