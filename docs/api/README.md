# ANC API

One HTTP API (API Gateway, `anc-prod-api`) serves every ANC service. This guide explains how to connect a client, in particular a browser frontend (Vite + React/JSX), to the read endpoints.

- Machine-readable contract: [openapi.yaml](openapi.yaml) (OpenAPI 3.1). Open it in any OpenAPI viewer (e.g. the Swagger Editor or the VS Code OpenAPI extension) to browse and try the endpoints.
- Infrastructure: [`infra/prod/api.tf`](../../infra/prod/api.tf) (API) and [`insights-api.tf`](../../infra/prod/insights-api.tf) (read endpoints).
- Authentication: **currently disabled**, the insights endpoints are public. Cognito is deployed and ready to be turned on: [../auth.md](../auth.md).

| Route | Auth | Service | Purpose |
| --- | --- | --- | --- |
| `POST /webhooks/youform` | YouForm signature | `youform-intake` | Receives YouForm submissions (not for clients) |
| `GET /insights/forms` | None (public) | `insights-api` | Readable forms and their submission counts |
| `GET /insights/forms/{form}/submissions` | None (public) | `insights-api` | Submissions of a form, paginated |
| `GET /insights/forms/{form}/submissions/{submission_id}` | None (public) | `insights-api` | One submission |
| `GET /insights/storage` | None (public) | `insights-api` | Raw submission files in S3: how many, in which folders |

## 1. Configuration

A client only needs the API base URL. It is kept out of this public repository; get it from Terraform with access to the state:

```bash
cd infra/prod
terraform output -json insights_web_config   # VITE_API_URL
```

Put it in the frontend's `.env.local` (git-ignored by Vite's default template):

```dotenv
VITE_API_URL=https://<api-id>.execute-api.us-east-1.amazonaws.com
```

Never put AWS credentials or other secrets in a frontend: everything in the bundle is public.

Quick check from a terminal:

```bash
curl https://<api-id>.execute-api.us-east-1.amazonaws.com/insights/forms
```

## 2. Connecting a Vite + React frontend

Browser calls are allowed only from the origins in `local.api_allowed_origins` ([`infra/prod/api.tf`](../../infra/prod/api.tf)); today `http://localhost:5173` (Vite's default dev server). Add the production frontend origin there before deploying it.

### Call the API

```js
// src/api.js
const API_URL = import.meta.env.VITE_API_URL;

export class ApiError extends Error {
  constructor(status, error, message) {
    super(message);
    this.status = status;
    this.error = error;
  }
}

async function apiGet(path, params = {}) {
  const url = new URL(`${API_URL}${path}`);
  for (const [key, value] of Object.entries(params)) {
    if (value != null) url.searchParams.set(key, value);
  }

  const response = await fetch(url);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new ApiError(response.status, body.error ?? "http_error", body.message ?? response.statusText);
  }
  return body;
}

export const listForms = () => apiGet("/insights/forms");

export const getSubmission = (form, submissionId) =>
  apiGet(`/insights/forms/${encodeURIComponent(form)}/submissions/${encodeURIComponent(submissionId)}`);

// Follows next_cursor until every submission of the form is loaded.
export async function listAllSubmissions(form) {
  const items = [];
  let cursor = null;
  do {
    const page = await apiGet(`/insights/forms/${encodeURIComponent(form)}/submissions`, { limit: 100, cursor });
    items.push(...page.items);
    cursor = page.next_cursor;
  } while (cursor);
  return items;
}
```

### Use it in a component

```jsx
// src/App.jsx
import { useEffect, useState } from "react";
import { listAllSubmissions } from "./api";

export default function App() {
  const [submissions, setSubmissions] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    listAllSubmissions("participant-feedback").then(setSubmissions).catch(setError);
  }, []);

  if (error) return <p>Could not load data: {error.message}</p>;
  return <p>{submissions.length} submissions</p>;
}
```

### Example: data for a chart

```js
// Counts how many submissions chose each option of one question (radio or checkbox).
export function countAnswers(submissions, fieldId) {
  const counts = {};
  for (const submission of submissions) {
    const answer = submission.answers.find((a) => a.field_id === fieldId)?.answer;
    for (const option of [answer].flat()) {
      if (option != null) counts[option] = (counts[option] ?? 0) + 1;
    }
  }
  return Object.entries(counts).map(([option, count]) => ({ option, count }));
}

// Net Promoter Score (-100..100) of an `nps` question.
export function npsScore(submissions, fieldId) {
  const scores = submissions
    .map((s) => s.answers.find((a) => a.field_id === fieldId)?.answer)
    .filter((value) => typeof value === "number");
  if (scores.length === 0) return null;
  const promoters = scores.filter((v) => v >= 9).length;
  const detractors = scores.filter((v) => v <= 6).length;
  return Math.round(((promoters - detractors) / scores.length) * 100);
}
```

Group answers by `field_id`, not by question text: the text can be edited in YouForm, the ID stays.

## 3. Endpoints

All responses are JSON (`application/json; charset=utf-8`) with `Cache-Control: no-store`. Full schemas in [openapi.yaml](openapi.yaml).

### `GET /insights/forms`

Forms that can be read and how many submissions each has.

```json
{ "items": [{ "form": "participant-feedback", "submission_count": 42 }] }
```

Only forms stored in DynamoDB are readable. `leader-self-assessment` is stored only in S3 by design and is not exposed.

### `GET /insights/forms/{form}/submissions`

| Query parameter | Default | Description |
| --- | --- | --- |
| `limit` | `50` | Page size, 1 to 100 |
| `cursor` | none | `next_cursor` from the previous page |

```json
{
  "items": [
    {
      "form": "participant-feedback",
      "submission_id": "x1y2z3w4v5",
      "form_name": "Retroalimentación Participantes (Reinicialo II - 2026)",
      "started_at": "2026-10-29T19:55:24-05:00",
      "completed_at": "2026-10-29T19:57:28-05:00",
      "received_at": "2026-10-29T19:57:28-05:00",
      "answers": [
        { "field_id": "abc123", "position": 4, "type": "radio", "question": "¿Qué edad tienes?", "answer": "18 - 21" },
        { "field_id": "def456", "position": 7, "type": "checkbox", "question": "¿Qué esperabas del retiro?", "answer": ["Option A", "Option B"] },
        { "field_id": "ghi789", "position": 58, "type": "nps", "question": "¿Qué tanto le recomendarías Reinícialo a un amigo?", "answer": 9 },
        { "field_id": "jkl012", "position": 62, "type": "textarea", "question": "Si pudieras mejorar algo, ¿cuál(es) sería(n)?" }
      ]
    }
  ],
  "next_cursor": "eyJzayI6ICJTVUJNSVNTSU9OI3gxeTJ6M3c0djUifQ"
}
```

- `next_cursor` is `null` on the last page. Treat it as opaque.
- Items are ordered by `submission_id`, not by date. Sort on the client (e.g. by `completed_at`).

### `GET /insights/forms/{form}/submissions/{submission_id}`

One submission, same shape as an item above.

### `GET /insights/storage`

Summary of the raw submission files in S3 (every form, including `leader-self-assessment`): how many files there are and in which folders. It never returns file names, contents or the bucket name.

```json
{
  "prefix": "submissions/",
  "files": 3,
  "bytes": 61234,
  "last_modified": "2026-10-29T19:57:29-05:00",
  "forms": [
    { "form": "leader-self-assessment", "files": 1, "bytes": 18000, "last_modified": "2026-10-29T18:10:02-05:00" },
    { "form": "participant-feedback", "files": 2, "bytes": 43234, "last_modified": "2026-10-29T19:57:29-05:00" }
  ],
  "folders": [
    { "path": "submissions/leader-self-assessment/2026/10/", "form": "leader-self-assessment", "files": 1, "bytes": 18000, "last_modified": "2026-10-29T18:10:02-05:00" },
    { "path": "submissions/participant-feedback/2026/10/", "form": "participant-feedback", "files": 2, "bytes": 43234, "last_modified": "2026-10-29T19:57:29-05:00" }
  ]
}
```

- Folders follow `submissions/<form>/<YYYY>/<MM>/` (month in Bogotá time) and are sorted by `path`. Only folders that contain files are listed.
- `forms` and the top-level fields aggregate `folders`. A file directly under `submissions/` (none expected) has `form: null`.
- `last_modified` is when the file was last written to S3, in Bogotá time; `null` when there are no files.
- S3 keeps one file per submission, so `files` per form can differ from `submission_count` in `GET /insights/forms` (DynamoDB), e.g. for S3-only forms.

## 4. Data model

**Submission**

| Field | Type | Notes |
| --- | --- | --- |
| `form` | string | Form slug, e.g. `participant-feedback` |
| `submission_id` | string | YouForm submission ID |
| `form_name` | string | Form title in YouForm |
| `started_at`, `completed_at`, `received_at` | string | ISO 8601 in Bogotá time, e.g. `2026-10-29T19:57:28-05:00`. Records stored before 2026-10-29 may be in UTC (`...Z` / `+00:00`); `new Date(value)` handles both |
| `answers` | array | Sorted by `position` |

**Answer**

| Field | Type | Notes |
| --- | --- | --- |
| `field_id` | string | Stable YouForm field ID. Use it as the key for charts |
| `position` | number | Order in the form |
| `type` | string | YouForm field type (`radio`, `checkbox`, `nps`, `opinion_scale`, `textarea`, ...) |
| `question` | string | Question text as it was when the submission arrived |
| `answer` | see below | **Absent** when the question was not answered |

| `type` | `answer` |
| --- | --- |
| `nps`, `opinion_scale`, `rating`, `number` | number (kept as text if YouForm sent something non-numeric) |
| `checkbox` | array of strings (YouForm joins options with `", "`; an option whose label contains `", "` is split in two) |
| anything else | string |

## 5. Errors

```json
{ "error": "not_found", "message": "Unknown form." }
```

| Status | `error` | When |
| --- | --- | --- |
| `400` | `invalid_parameter` | `limit` out of range or invalid `cursor` |
| `404` | `not_found` | Unknown form, submission or route |
| `429` | (API Gateway: `{"message": "Too Many Requests"}`) | Throttled; retry with backoff |
| `500` | `internal_error` | Unexpected error; details only in the Lambda logs |

When authentication is turned on, `401` (missing or invalid token) and `403` (user not in `insights-readers`) are added; see [../auth.md](../auth.md).

## 6. Security and limits

- **The insights endpoints are public**: anyone with the URL can read every submission, including free-text answers. This is a temporary decision ([../decisions.md](../decisions.md)); do not publish the URL, and turn authentication on ([../auth.md](../auth.md)) before sharing the frontend widely.
- CORS only lets browsers on `local.api_allowed_origins` call the API. It does not stop direct requests (curl, scripts).
- The Lambda can only `Query` and `GetItem` the DynamoDB partitions of readable forms (IAM `dynamodb:LeadingKeys`), and list file names under `submissions/` in S3 (`s3:ListBucket` with an `s3:prefix` condition). It cannot write, scan, or read any S3 file.
- Throttling: 10 requests/second steady, burst 20, shared by the whole API (including the YouForm webhook).
- Logs carry route, status and error code only; never answers.
- Responses contain personal answers. Do not store them in `localStorage`, analytics tools or error trackers.
