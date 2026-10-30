"""Insights API: read-only access to normalized YouForm submissions in DynamoDB.

With READER_GROUP set, API Gateway validates the Cognito access token (JWT authorizer) and this
function additionally requires membership in that group. Without it, the API is public.
Only forms stored in DynamoDB are readable.

Answers are never logged; logs only carry route, form slug and outcome.
"""

import base64
import binascii
import json
import logging
import os
import re
from decimal import Decimal, InvalidOperation
from typing import Any

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DEFAULT_LIMIT = 50
MAX_LIMIT = 100
SUBMISSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
SUBMISSION_ATTRIBUTES = ("submission_id", "form_name", "started_at", "completed_at", "received_at")
ANSWER_ATTRIBUTES = ("position", "type", "question")
# YouForm sends every answer as a string; these types are returned as numbers.
NUMERIC_TYPES = {"nps", "opinion_scale", "rating", "number"}
# YouForm joins the selected options of a checkbox with ", "; they are returned as a list.
MULTIPLE_CHOICE_TYPES = {"checkbox"}

_clients: dict[str, Any] = {}


class ApiError(Exception):
    def __init__(self, status_code: int, error: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.error = error
        self.message = message


def _responses_table() -> Any:
    if "responses_table" not in _clients:
        import boto3

        _clients["responses_table"] = boto3.resource("dynamodb").Table(os.environ["RESPONSES_TABLE"])
    return _clients["responses_table"]


def _forms() -> dict[str, str]:
    """Readable forms: {slug: form_id}."""
    return json.loads(os.environ["FORMS_CONFIG"])


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, set):
        return sorted(value)
    raise TypeError(f"Not JSON serializable: {type(value).__name__}")


def _response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        # Responses carry personal data: never cache them in browsers or proxies.
        "headers": {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"},
        "body": json.dumps(body, default=_json_default, ensure_ascii=False),
    }


def _groups(event: dict[str, Any]) -> set[str]:
    claims = event.get("requestContext", {}).get("authorizer", {}).get("jwt", {}).get("claims", {})
    groups = claims.get("cognito:groups", [])
    # HTTP API passes array claims as a string such as "[readers admins]".
    if isinstance(groups, str):
        groups = groups.strip("[]").replace(",", " ").split()
    return set(groups)


def _form_id(event: dict[str, Any]) -> tuple[str, str]:
    slug = (event.get("pathParameters") or {}).get("form", "")
    form_id = _forms().get(slug)
    if form_id is None:
        raise ApiError(404, "not_found", "Unknown form.")
    return slug, form_id


def _limit(params: dict[str, str]) -> int:
    raw = params.get("limit", str(DEFAULT_LIMIT))
    if not raw.isdigit() or not 1 <= int(raw) <= MAX_LIMIT:
        raise ApiError(400, "invalid_parameter", f"limit must be an integer between 1 and {MAX_LIMIT}.")
    return int(raw)


def _encode_cursor(last_key: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps({"sk": last_key["sk"]}).encode()).decode().rstrip("=")


def _decode_cursor(cursor: str, form_id: str) -> dict[str, str]:
    try:
        decoded = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        sk = decoded["sk"]
    except (binascii.Error, UnicodeDecodeError, ValueError, TypeError, KeyError):
        raise ApiError(400, "invalid_parameter", "cursor is not valid.") from None
    if not isinstance(sk, str) or not sk.startswith("SUBMISSION#"):
        raise ApiError(400, "invalid_parameter", "cursor is not valid.")
    return {"pk": f"FORM#{form_id}", "sk": sk}


def _answer_value(answer_type: Any, value: Any) -> Any:
    if not isinstance(value, str):
        return value
    if answer_type in NUMERIC_TYPES:
        try:
            number = Decimal(value.strip())
        except InvalidOperation:
            return value
        return number if number.is_finite() else value
    if answer_type in MULTIPLE_CHOICE_TYPES:
        return [option.strip() for option in value.split(", ") if option.strip()]
    return value


def _answer(field_id: str, stored: dict[str, Any]) -> dict[str, Any]:
    answer = {"field_id": field_id, **{key: stored[key] for key in ANSWER_ATTRIBUTES if key in stored}}
    if "answer" in stored:
        answer["answer"] = _answer_value(stored.get("type"), stored["answer"])
    return answer


def _submission(item: dict[str, Any], slug: str) -> dict[str, Any]:
    answers = [_answer(field_id, stored) for field_id, stored in (item.get("answers") or {}).items()]
    answers.sort(key=lambda answer: (answer.get("position", 0), answer["field_id"]))
    return {
        "form": slug,
        **{key: item.get(key) for key in SUBMISSION_ATTRIBUTES},
        "answers": answers,
    }


def _list_forms(_event: dict[str, Any]) -> dict[str, Any]:
    forms = []
    for slug, form_id in sorted(_forms().items()):
        query = {
            "KeyConditionExpression": "pk = :pk",
            "ExpressionAttributeValues": {":pk": f"FORM#{form_id}"},
            "Select": "COUNT",
        }
        count = 0
        while True:
            result = _responses_table().query(**query)
            count += result["Count"]
            if "LastEvaluatedKey" not in result:
                break
            query["ExclusiveStartKey"] = result["LastEvaluatedKey"]
        forms.append({"form": slug, "submission_count": count})
    return {"items": forms}


def _list_submissions(event: dict[str, Any]) -> dict[str, Any]:
    slug, form_id = _form_id(event)
    params = event.get("queryStringParameters") or {}
    query = {
        "KeyConditionExpression": "pk = :pk",
        "ExpressionAttributeValues": {":pk": f"FORM#{form_id}"},
        "Limit": _limit(params),
    }
    if params.get("cursor"):
        query["ExclusiveStartKey"] = _decode_cursor(params["cursor"], form_id)

    result = _responses_table().query(**query)
    last_key = result.get("LastEvaluatedKey")
    return {
        "items": [_submission(item, slug) for item in result.get("Items", [])],
        "next_cursor": _encode_cursor(last_key) if last_key else None,
    }


def _get_submission(event: dict[str, Any]) -> dict[str, Any]:
    slug, form_id = _form_id(event)
    submission_id = (event.get("pathParameters") or {}).get("submission_id", "")
    if not SUBMISSION_ID_PATTERN.match(submission_id):
        raise ApiError(404, "not_found", "Unknown submission.")
    item = _responses_table().get_item(
        Key={"pk": f"FORM#{form_id}", "sk": f"SUBMISSION#{submission_id}"}
    ).get("Item")
    if item is None:
        raise ApiError(404, "not_found", "Unknown submission.")
    return _submission(item, slug)


ROUTES = {
    "GET /insights/forms": _list_forms,
    "GET /insights/forms/{form}/submissions": _list_submissions,
    "GET /insights/forms/{form}/submissions/{submission_id}": _get_submission,
}


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    route = event.get("routeKey", "")
    action = ROUTES.get(route)
    try:
        if action is None:
            raise ApiError(404, "not_found", "Unknown route.")
        # No READER_GROUP means public mode (auth disabled in Terraform, see docs/auth.md).
        reader_group = os.environ.get("READER_GROUP")
        if reader_group and reader_group not in _groups(event):
            raise ApiError(403, "forbidden", "User is not allowed to read insights.")
        body = action(event)
    except ApiError as error:
        logger.warning(json.dumps({"route": route, "status": error.status_code, "error": error.error}))
        return _response(error.status_code, {"error": error.error, "message": error.message})
    except Exception:
        logger.exception("Insights request failed on route %s.", route)
        return _response(500, {"error": "internal_error", "message": "Unexpected error."})

    logger.info(json.dumps({"route": route, "status": 200}))
    return _response(200, body)
