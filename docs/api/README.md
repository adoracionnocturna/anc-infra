# ANC API

One HTTP API (API Gateway, `anc-prod-api`) serves every ANC service. This guide explains how to connect a client, in particular a browser frontend (Vite + React/JSX), to the read endpoints.

- Machine-readable contract: [openapi.yaml](openapi.yaml) (OpenAPI 3.1). Open it in any OpenAPI viewer (e.g. the Swagger Editor or the VS Code OpenAPI extension) to browse and try the endpoints.
- Infrastructure: [`infra/prod/api.tf`](../../infra/prod/api.tf) (API), [`auth.tf`](../../infra/prod/auth.tf) (users), [`insights-api.tf`](../../infra/prod/insights-api.tf) (read endpoints).

| Route | Auth | Service | Purpose |
| --- | --- | --- | --- |
| `POST /webhooks/youform` | YouForm signature | `youform-intake` | Receives YouForm submissions (not for clients) |
| `GET /insights/forms` | Cognito access token + `insights-readers` | `insights-api` | Readable forms and their submission counts |
| `GET /insights/forms/{form}/submissions` | Cognito access token + `insights-readers` | `insights-api` | Submissions of a form, paginated |
| `GET /insights/forms/{form}/submissions/{submission_id}` | Cognito access token + `insights-readers` | `insights-api` | One submission |

## 1. Configuration values

A client needs four values. They are not secrets (they end up in the browser bundle), but they are kept out of this public repository. Get them from Terraform with access to the state:

```bash
cd infra/prod
terraform output -json insights_web_config
```

Put them in the frontend's `.env.local` (git-ignored by Vite's default template):

```dotenv
VITE_API_URL=https://<api-id>.execute-api.us-east-1.amazonaws.com
VITE_AWS_REGION=us-east-1
VITE_COGNITO_USER_POOL_ID=us-east-1_xxxxxxxxx
VITE_COGNITO_CLIENT_ID=xxxxxxxxxxxxxxxxxxxxxxxxxx
```

Never put AWS credentials, API keys or any other secret in a frontend: everything in the bundle is public.

## 2. Users and access

Users live in the Cognito user pool `anc-prod-users`:

- No self sign-up: an administrator creates every user.
- No emails are sent. Temporary passwords are shared out of band, and forgotten passwords are reset by an administrator.
- Reading insights requires membership in the group `insights-readers`. A valid user outside the group gets `403`.
- Passwords: at least 12 characters with lowercase, uppercase, numbers and symbols.
- Tokens: the access and ID tokens last 1 hour and the refresh token 7 days. Refresh tokens can be revoked.

Administrator commands (AWS CLI with permissions on the pool; `<pool_id>` is `VITE_COGNITO_USER_POOL_ID`):

```bash
# Create a user with a temporary password (changed at first sign-in) and grant read access.
aws cognito-idp admin-create-user --user-pool-id <pool_id> --username person@example.org --user-attributes Name=email,Value=person@example.org Name=email_verified,Value=true --temporary-password '<Temporary-Password-123>' --message-action SUPPRESS
aws cognito-idp admin-add-user-to-group --user-pool-id <pool_id> --username person@example.org --group-name insights-readers

# Reset a forgotten password (new temporary password).
aws cognito-idp admin-set-user-password --user-pool-id <pool_id> --username person@example.org --password '<Temporary-Password-456>' --no-permanent

# Remove access: leave the group, end every session, disable the user.
aws cognito-idp admin-remove-user-from-group --user-pool-id <pool_id> --username person@example.org --group-name insights-readers
aws cognito-idp admin-user-global-sign-out --user-pool-id <pool_id> --username person@example.org
aws cognito-idp admin-disable-user --user-pool-id <pool_id> --username person@example.org

# List members of the group.
aws cognito-idp list-users-in-group --user-pool-id <pool_id> --group-name insights-readers --query "Users[].Username"
```

An access token that was already issued stays valid until it expires (at most 1 hour), even after the user is removed or signed out.

### Testing from the command line

Browsers sign in with SRP, which the AWS CLI cannot do. For tests, administrators use `ADMIN_USER_PASSWORD_AUTH`, which only works with AWS credentials allowed to call `cognito-idp:AdminInitiateAuth`, so it is not usable from a browser. The tokens are real and go through the same JWT authorizer as the frontend's.

```bash
# <client_id> is VITE_COGNITO_CLIENT_ID; <api_url> is VITE_API_URL.
aws cognito-idp admin-initiate-auth --user-pool-id <pool_id> --client-id <client_id> --auth-flow ADMIN_USER_PASSWORD_AUTH --auth-parameters USERNAME=person@example.org,PASSWORD='<password>'
# First sign-in returns ChallengeName NEW_PASSWORD_REQUIRED: set the permanent password.
aws cognito-idp admin-respond-to-auth-challenge --user-pool-id <pool_id> --client-id <client_id> --challenge-name NEW_PASSWORD_REQUIRED --session '<Session>' --challenge-responses USERNAME='<USER_ID_FOR_SRP>',NEW_PASSWORD='<new password>'
# Use AuthenticationResult.AccessToken:
curl -H "Authorization: Bearer <access_token>" <api_url>/insights/forms
```

## 3. Connecting a Vite + React frontend

Install [AWS Amplify](https://docs.amplify.aws/react/build-a-backend/auth/connect-your-frontend/) (only its Auth category is used; no Amplify backend is needed):

```bash
npm install aws-amplify @aws-amplify/ui-react
```

### Configure and sign in

The `Authenticator` component handles sign-in and the forced password change after the first sign-in. Sign-up is hidden because users are created by an administrator.

```jsx
// src/main.jsx
import React from "react";
import ReactDOM from "react-dom/client";
import { Amplify } from "aws-amplify";
import { Authenticator } from "@aws-amplify/ui-react";
import "@aws-amplify/ui-react/styles.css";
import App from "./App";

Amplify.configure({
  Auth: {
    Cognito: {
      userPoolId: import.meta.env.VITE_COGNITO_USER_POOL_ID,
      userPoolClientId: import.meta.env.VITE_COGNITO_CLIENT_ID,
    },
  },
});

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <Authenticator hideSignUp>
      {({ signOut }) => <App signOut={signOut} />}
    </Authenticator>
  </React.StrictMode>,
);
```

If you build your own sign-in form, use `signIn` and handle the first-sign-in challenge:

```js
import { signIn, confirmSignIn } from "aws-amplify/auth";

const { nextStep } = await signIn({ username: email, password });
if (nextStep.signInStep === "CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED") {
  await confirmSignIn({ challengeResponse: newPassword });
}
```

### Call the API

Send the **access token** (not the ID token) in the `Authorization` header. `fetchAuthSession` refreshes it automatically when it expires.

```js
// src/api.js
import { fetchAuthSession } from "aws-amplify/auth";

const API_URL = import.meta.env.VITE_API_URL;

export class ApiError extends Error {
  constructor(status, error, message) {
    super(message);
    this.status = status;
    this.error = error;
  }
}

async function apiGet(path, params = {}) {
  const { tokens } = await fetchAuthSession();
  if (!tokens?.accessToken) throw new ApiError(401, "unauthorized", "Not signed in.");

  const url = new URL(`${API_URL}${path}`);
  for (const [key, value] of Object.entries(params)) {
    if (value != null) url.searchParams.set(key, value);
  }

  const response = await fetch(url, {
    headers: { Authorization: `Bearer ${tokens.accessToken.toString()}` },
  });
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

## 4. Endpoints

All responses are JSON with `Cache-Control: no-store`. Full schemas in [openapi.yaml](openapi.yaml).

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

## 5. Data model

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

## 6. Errors

```json
{ "error": "not_found", "message": "Unknown form." }
```

| Status | `error` | When |
| --- | --- | --- |
| `400` | `invalid_parameter` | `limit` out of range or invalid `cursor` |
| `401` | (API Gateway: `{"message": "Unauthorized"}`) | Missing, invalid or expired access token. Refresh the session or sign in again |
| `403` | `forbidden` | Valid user, but not in `insights-readers` |
| `404` | `not_found` | Unknown form, submission or route |
| `429` | (API Gateway: `{"message": "Too Many Requests"}`) | Throttled; retry with backoff |
| `500` | `internal_error` | Unexpected error; details only in the Lambda logs |

## 7. Security and limits

- The API Gateway JWT authorizer validates the token signature, issuer, expiry and app client before the Lambda runs. The Lambda also checks the group.
- The Lambda can only `Query` and `GetItem` the DynamoDB partitions of readable forms (IAM `dynamodb:LeadingKeys`). It cannot write, scan, or read S3.
- CORS only allows the origins listed in `local.api_allowed_origins` (`infra/prod/api.tf`), with method `GET` and header `Authorization`. Add the production frontend origin there before deploying it.
- Throttling: 10 requests/second steady, burst 20, shared by the whole API.
- Logs carry route, status and error code only; never answers or tokens.
- Responses contain personal answers. Do not store them in `localStorage`, analytics tools or error trackers.
