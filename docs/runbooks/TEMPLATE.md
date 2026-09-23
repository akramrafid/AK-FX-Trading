# Runbook: {{Incident or procedure name}}

- **Service:** {{}}
- **Severity mapping:** SEV1 (user-facing outage) / SEV2 (degraded) / SEV3 (contained)
- **Owner on-call:** {{}}

## Symptoms

{{}}

## Immediate actions (first 5 minutes)

1. Check `/health/live` and `/health/ready`
2. Check error budget burn and last deploy SHA
3. {{}}

## Diagnosis

{{}}

## Mitigation

- Rollback: `{{command}}`
- Feature flag kill switch: `{{flag}}`

## Recovery / restore

- Backup restore verified in staging: {{yes/no}}
- PITR command: `{{command}}`

## Follow-up

- Incident doc:
- Hardening task IDs:
