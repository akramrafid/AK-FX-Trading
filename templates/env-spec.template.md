# Environment Variable Specification

Every variable used by app, worker, or CI. Mirror into `.env.example`. Never commit secrets.

| Name | Required | Default | Purpose | Example (redacted) |
|---|---|---|---|---|
| `NODE_ENV` / `APP_ENV` | yes | `development` | Runtime environment | `production` |
| `DATABASE_URL` | yes | — | Primary datastore | `postgres://user:***@host:5432/db` |
| `REDIS_URL` | no | — | Cache / queue | `redis://***@host:6379` |
| `LOG_LEVEL` | no | `info` | Structured log verbosity | `info` |
| `SENTRY_DSN` | no | — | Error tracking | `https://***@sentry.io/***` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | no | — | Trace export | `http://localhost:4318` |
