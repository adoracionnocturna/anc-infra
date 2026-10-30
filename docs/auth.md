# Authentication (Cognito)

> **Status: deployed but not enforced.** The insights API is temporarily public (`insights_require_auth = false` in [`infra/prod/insights-api.tf`](../infra/prod/insights-api.tf)); see [decisions.md](decisions.md). Everything below is ready to be turned on.

## Current setup

Terraform: [`infra/prod/auth.tf`](../infra/prod/auth.tf) (user pool, app client) and [`infra/prod/insights-api.tf`](../infra/prod/insights-api.tf) (group, switch).

| Item | Setting |
| --- | --- |
| User pool | `anc-prod-users`, shared by ANC web apps; sign-in with email + password |
| Sign-up | Disabled: an administrator creates every user |
| Emails | None sent. Temporary passwords are shared out of band; forgotten passwords are reset by an administrator |
| Passwords | 12+ characters with lowercase, uppercase, numbers and symbols |
| MFA | Off |
| App client | `anc-prod-insights-web`: public (no secret), SRP sign-in for browsers, `ADMIN_USER_PASSWORD_AUTH` for administrators testing from the CLI |
| Tokens | Access and ID tokens 1 hour, refresh token 7 days, revocable |
| Access to insights | Membership in the group `insights-readers` |
| Enforcement (when enabled) | API Gateway JWT authorizer validates the access token (`401`); the Lambda requires the group (`403`) |

**Where allowed emails live.** Only in Cognito: users of the pool can sign in, members of `insights-readers` can read insights. Emails are personal data and are never stored in this repository or in GitHub variables or secrets. Granting or removing access is an administrator command, not a code change.

## Turning authentication on

1. Set `insights_require_auth = true` in `infra/prod/insights-api.tf`.
2. Add the frontend origin to `local.api_allowed_origins` in `infra/prod/api.tf` if it is not there.
3. Update [api/README.md](api/README.md) and [api/openapi.yaml](api/openapi.yaml): auth column, `401`/`403` errors, `security` (`cognitoAccessToken`), and the frontend sign-in from [Frontend](#frontend-vite--react) below.
4. Create the users and add them to the group (below), then push.

The frontend gets the pool and client IDs from `terraform output -json insights_web_config` (`VITE_COGNITO_USER_POOL_ID`, `VITE_COGNITO_CLIENT_ID`).

## Users

Administrator commands (AWS CLI with permissions on the pool):

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
aws cognito-idp list-users-in-group --user-pool-id <pool_id> --group-name insights-readers --query "Users[].Attributes[?Name=='email'].Value"
```

An access token that was already issued stays valid until it expires (at most 1 hour), even after the user is removed or signed out.

### Testing from the command line

Browsers sign in with SRP, which the AWS CLI cannot do. Administrators use `ADMIN_USER_PASSWORD_AUTH`, which requires AWS credentials allowed to call `cognito-idp:AdminInitiateAuth`, so it is not usable from a browser. The tokens are real and go through the same JWT authorizer as the frontend's.

```bash
aws cognito-idp admin-initiate-auth --user-pool-id <pool_id> --client-id <client_id> --auth-flow ADMIN_USER_PASSWORD_AUTH --auth-parameters USERNAME=person@example.org,PASSWORD='<password>'
# First sign-in returns ChallengeName NEW_PASSWORD_REQUIRED: set the permanent password.
aws cognito-idp admin-respond-to-auth-challenge --user-pool-id <pool_id> --client-id <client_id> --challenge-name NEW_PASSWORD_REQUIRED --session '<Session>' --challenge-responses USERNAME='<USER_ID_FOR_SRP>',NEW_PASSWORD='<new password>'
# Use AuthenticationResult.AccessToken:
curl -H "Authorization: Bearer <access_token>" <api_url>/insights/forms
```

## Frontend (Vite + React)

Install [AWS Amplify](https://docs.amplify.aws/react/build-a-backend/auth/connect-your-frontend/) (only its Auth category; no Amplify backend):

```bash
npm install aws-amplify @aws-amplify/ui-react
```

The `Authenticator` component handles sign-in and the forced password change at first sign-in. Sign-up is hidden because users are created by an administrator.

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

A custom sign-in form uses `signIn` and handles the first-sign-in challenge:

```js
import { signIn, confirmSignIn } from "aws-amplify/auth";

const { nextStep } = await signIn({ username: email, password });
if (nextStep.signInStep === "CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED") {
  await confirmSignIn({ challengeResponse: newPassword });
}
```

Requests send the **access token** (not the ID token); `fetchAuthSession` refreshes it when it expires. In the `apiGet` helper of [api/README.md](api/README.md), add:

```js
import { fetchAuthSession } from "aws-amplify/auth";

const { tokens } = await fetchAuthSession();
const headers = { Authorization: `Bearer ${tokens.accessToken.toString()}` };
```

## Roadmap

Not built yet; recorded so it can be picked up later.

| Option | What it takes | Notes |
| --- | --- | --- |
| **Sign in with Google** (preferred next step) | OAuth client in Google Cloud Console (client secret as a GitHub secret), Cognito prefix domain (`<prefix>.auth.us-east-1.amazoncognito.com`, no custom domain), managed login, callback URLs for local and production, `signInWithRedirect({ provider: "Google" })` in the frontend | Add a **pre sign-up Lambda trigger**: Google lets anyone with a Google account complete sign-in, so the trigger links the Google identity to a user pre-created by an administrator and rejects unknown emails. The allowlist stays in Cognito |
| Microsoft, Apple, Facebook | Same as Google with each provider's console | Only if users live there |
| MFA (TOTP) | Configuration change in `auth.tf` plus the MFA steps in the frontend | When the audience grows |
| Email codes or passkeys | Cognito sends emails | Conflicts with "no emails" today |
