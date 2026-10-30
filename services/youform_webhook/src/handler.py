"""YouForm webhook receiver.

Verifies the HMAC-SHA256 `Signature` header with the form's signing secret, stores the raw
payload in S3 and, for forms flagged `store_in_dynamodb`, a normalized record in DynamoDB.

Answers are never logged; logs only carry form slug, submission ID and outcome.
"""

import base64
import binascii
import hashlib
import hmac
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SUBMISSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
FIELD_ATTRIBUTES = ("question", "type", "answer", "position")
# Bogotá is UTC-5 all year (no daylight saving time), so a fixed offset is exact.
BOGOTA = timezone(timedelta(hours=-5), "America/Bogota")

_signing_secrets: dict[str, str] | None = None
_clients: dict[str, Any] = {}


def _client(service: str) -> Any:
    if service not in _clients:
        import boto3

        _clients[service] = boto3.client(service)
    return _clients[service]


def _responses_table() -> Any:
    if "responses_table" not in _clients:
        import boto3

        _clients["responses_table"] = boto3.resource("dynamodb").Table(os.environ["RESPONSES_TABLE"])
    return _clients["responses_table"]


def _forms() -> dict[str, dict[str, Any]]:
    return json.loads(os.environ["FORMS_CONFIG"])


def _load_signing_secrets() -> dict[str, str]:
    global _signing_secrets
    if _signing_secrets is None:
        response = _client("secretsmanager").get_secret_value(SecretId=os.environ["SECRET_ID"])
        _signing_secrets = json.loads(response["SecretString"])
    return _signing_secrets


def _response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def _raw_body(event: dict[str, Any]) -> bytes:
    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        return base64.b64decode(body, validate=True)
    return body.encode("utf-8")


def _header(event: dict[str, Any], name: str) -> str | None:
    for key, value in (event.get("headers") or {}).items():
        if key.lower() == name:
            return value
    return None


def _valid_signature(raw_body: bytes, signature: str | None, secret: str) -> bool:
    if not signature:
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip().lower())


def _bogota_time(value: Any) -> datetime | None:
    """Parses a YouForm timestamp (UTC, e.g. "2026-10-30T00:57:28.000000Z") into Bogotá time."""
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(BOGOTA)


def _bogota_iso(value: Any) -> Any:
    """ISO 8601 in Bogotá time with explicit offset; unparseable values are kept as received."""
    parsed = _bogota_time(value)
    return parsed.isoformat(timespec="seconds") if parsed else value


def _s3_key(slug: str, submission_id: str, completed_at: Any, received_at: datetime) -> str:
    submitted = _bogota_time(completed_at) or received_at.astimezone(BOGOTA)
    return f"submissions/{slug}/{submitted:%Y}/{submitted:%m}/{submission_id}.json"


def _normalized_answers(fields: Any) -> dict[str, dict[str, Any]]:
    answers: dict[str, dict[str, Any]] = {}
    for field in fields if isinstance(fields, list) else []:
        if not isinstance(field, dict) or not field.get("id"):
            continue
        answers[str(field["id"])] = {
            key: field[key] for key in FIELD_ATTRIBUTES if field.get(key) not in (None, "")
        }
    return answers


def _dynamodb_item(payload: dict[str, Any], slug: str, s3_key: str, received_at: datetime) -> dict[str, Any]:
    item = {
        "pk": f"FORM#{payload['form_id']}",
        "sk": f"SUBMISSION#{payload['submission_id']}",
        "form_id": payload["form_id"],
        "form_slug": slug,
        "form_name": payload.get("form_name"),
        "submission_id": payload["submission_id"],
        "started_at": _bogota_iso(payload.get("started_at")),
        "completed_at": _bogota_iso(payload.get("completed_at")),
        "received_at": _bogota_iso(received_at),
        "raw_s3_key": s3_key,
        "answers": _normalized_answers(payload.get("fields")),
    }
    return {key: value for key, value in item.items() if value is not None}


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    received_at = datetime.now(timezone.utc)

    try:
        raw_body = _raw_body(event)
        # Decimal keeps numbers compatible with DynamoDB, which rejects floats.
        payload = json.loads(raw_body, parse_float=Decimal)
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError):
        logger.warning("Rejected webhook: body is not valid JSON.")
        return _response(400, {"ok": False, "error": "invalid_payload"})
    if not isinstance(payload, dict):
        logger.warning("Rejected webhook: body is not a JSON object.")
        return _response(400, {"ok": False, "error": "invalid_payload"})

    form_id = str(payload.get("form_id") or "")
    form = _forms().get(form_id)
    if form is None:
        logger.warning("Rejected webhook: form %r is not configured.", form_id[:32])
        return _response(401, {"ok": False, "error": "unauthorized"})

    try:
        secret = _load_signing_secrets().get(form_id)
    except Exception:
        logger.exception("Could not load signing secrets.")
        return _response(500, {"ok": False, "error": "configuration_error"})
    if not secret:
        logger.error("No signing secret configured for form %s.", form["slug"])
        return _response(500, {"ok": False, "error": "configuration_error"})

    if not _valid_signature(raw_body, _header(event, "signature"), secret):
        logger.warning("Rejected webhook for form %s: invalid signature.", form["slug"])
        return _response(401, {"ok": False, "error": "unauthorized"})

    submission_id = str(payload.get("submission_id") or "")
    if not SUBMISSION_ID_PATTERN.match(submission_id):
        logger.warning("Rejected webhook for form %s: invalid submission_id.", form["slug"])
        return _response(400, {"ok": False, "error": "invalid_submission_id"})

    s3_key = _s3_key(form["slug"], submission_id, payload.get("completed_at"), received_at)
    stored_in_dynamodb = bool(form.get("store_in_dynamodb"))
    try:
        _client("s3").put_object(
            Bucket=os.environ["SUBMISSIONS_BUCKET"],
            Key=s3_key,
            Body=raw_body,
            ContentType="application/json",
        )
        if stored_in_dynamodb:
            _responses_table().put_item(Item=_dynamodb_item(payload, form["slug"], s3_key, received_at))
    except Exception:
        logger.exception("Failed to store submission %s for form %s.", submission_id, form["slug"])
        return _response(500, {"ok": False, "error": "storage_error"})

    logger.info(
        json.dumps(
            {
                "message": "Stored YouForm submission",
                "form": form["slug"],
                "submission_id": submission_id,
                "s3_key": s3_key,
                "stored_in_dynamodb": stored_in_dynamodb,
            }
        )
    )
    return _response(200, {"ok": True, "submission_id": submission_id})
