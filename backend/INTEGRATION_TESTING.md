# MySQL integration tests

Integration tests must be selected explicitly with both:

- `DEVTRACK_DB_MODE=integration`
- `pytest --integration -m integration`

The application does not load `backend/.env` in integration mode. Instead,
provide all of these environment variables before starting pytest or Alembic:

- `INTEGRATION_DB_HOST`
- `INTEGRATION_DB_PORT`
- `INTEGRATION_DB_NAME=devtrack_integration_test`
- `INTEGRATION_DB_USER` (an explicitly named dedicated account)
- `INTEGRATION_DB_PASSWORD`
- `INTEGRATION_DB_SSL_CA` (required for non-loopback hosts; path to trusted CA)
- `JWT_SECRET_KEY` (a test-only value with at least 32 characters)

The integration database name is fixed to avoid accidentally selecting the
normal `devtrack` database. `INTEGRATION_DB_USER` must identify a dedicated
account, not a root or development account. Create it with grants limited to
`devtrack_integration_test.*`, without `GRANT OPTION` or role-based grants.
The account name is explicit and need not match the database name.

Loopback hosts (`localhost`, `127.0.0.1`, and `::1`) may use local MySQL without
TLS. All other hosts require `INTEGRATION_DB_SSL_CA`; PyMySQL verifies both the
certificate chain and server hostname. Do not disable identity verification.

Before every pool checkout, the application checks `DATABASE()`,
`CURRENT_USER()` and `SHOW GRANTS`. An unverified connection is invalidated
before SQLAlchemy can hand it to application code. Alembic online migrations
use this same guarded engine.

Normal unit tests:

```powershell
python -m pytest backend/tests
```

Integration tests (the complete marker expression is required):

```powershell
$env:DEVTRACK_DB_MODE = "integration"
$env:INTEGRATION_DB_HOST = "127.0.0.1"
$env:INTEGRATION_DB_PORT = "3306"
$env:INTEGRATION_DB_NAME = "devtrack_integration_test"
$env:INTEGRATION_DB_USER = "devtrack_test_runner"
$env:INTEGRATION_DB_PASSWORD = "<provided-out-of-band>"
$env:JWT_SECRET_KEY = "<test-only value of at least 32 characters>"
python -m pytest --integration -m integration backend/tests
```

Set `INTEGRATION_DB_SSL_CA` for a remote database. The `--integration` hook
validates the explicit settings before test modules are imported and rejects
any marker selection other than exactly `-m integration`. Tests must be marked
with `@pytest.mark.integration`. If integration mode is set without
`--integration`, pytest exits before collection. Do not put integration
settings in `backend/.env`.

No integration database or service is created by this repository configuration.
Before running integration tests, provision a disposable MySQL instance and the
dedicated least-privilege account manually. Apply the full Alembic revision
chain only to that database, verify the target and grants, and destroy the
disposable instance after the test run.

Invitation integration tests must replace
`app.api.routes.organization_invitations.send_invitation_email` with a mock
before making requests. They must not use real SMTP credentials or contact a
mail provider.
