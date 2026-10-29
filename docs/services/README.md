# Service catalog

Every service deployed from this repository. Update this file in the same commit that adds or changes a service.

| Service | Status | Entry point | Terraform | Code |
| --- | --- | --- | --- | --- |
| `youform-intake` | Planned | `POST` webhook from YouForm | `infra/prod/youform-intake.tf` | `services/youform_webhook/` |

---

## youform-intake

**Status:** planned.

**Purpose.** Receive YouForm submissions through a webhook and store them: the raw payload in S3 and a normalized record in DynamoDB.

**Forms (features).**

| Form ID | Slug | Name |
| --- | --- | --- |
| `ajbsvmgt` | `participant-feedback` | Retroalimentación Participantes (Reinicialo II - 2026) |
| `txrpjpz3` | `leader-self-assessment` | Autoevaluación Líderes (Reinicialo II - 2026) |

**Resources.** To be documented when implemented.

**Data layout.** To be documented when implemented.

---

## Template for a new service

```markdown
## <service-name>

**Status:** planned | active | deprecated.

**Purpose.** One or two sentences.

**Entry point.** Webhook / schedule / queue, and who calls it.

**Features.** Configured variants (forms, sources, ...).

**Resources.** AWS resources and their names (without account IDs).

**Data layout.** Keys, S3 prefixes, retention.

**Operations.** Where to look when it fails (log group, alarms), how to re-process.
```
