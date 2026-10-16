# Organization invitations

## API contract

- `POST /organizations/{organization_id}/invitations` creates or rotates an
  invitation. The JSON response contains the invitation metadata and derived
  status, but never the raw token or its hash.
- `GET /organizations/{organization_id}/invitations` lists organization
  invitations. `GET /users/me/invitations` lists pending invitations addressed
  to the authenticated user's email.
- `POST /users/me/invitations/{invitation_id}/accept` accepts an invitation.
  `POST /users/me/invitations/{invitation_id}/reject` rejects it. Both require
  a JSON body of `{"token": "<token from the invitation email>"}`.
- `POST /organizations/{organization_id}/invitations/{invitation_id}/revoke`
  lets an organization owner or admin revoke a pending invitation.

The email link currently targets
`{APP_BASE_URL}/invitations/accept?invitation_id={id}&token={token}`. No
frontend acceptance page exists yet. The frontend should read these query
parameters and submit the invitation ID and token to the accept API endpoint;
the email URL is a proposed integration contract, not a route implemented by
this backend.

If delivery fails, creation returns HTTP 502 after persisting the invitation.
Retrying the create request reuses the pending record and rotates its token, so
the previously generated token becomes invalid.

Invitation creation, acceptance, administrative revocation, and direct member
management acquire locks in organization → actor/target membership →
invitation order. Acceptance first reads the invitation's organization ID
without a lock, then locks the organization, rechecks the target membership
under that lock, and finally locks and refreshes the invitation before
validating it. This lets creation or direct member addition observe a
membership committed by a competing acceptance before creating or renewing an
invitation. Direct member addition revokes any pending invitations for that
user as part of the same transaction.

These lock-order and race guarantees have not been verified against a running
MySQL/InnoDB instance. The unit tests inspect generated locking queries and
exercise the post-lock membership check, but do not establish real isolation or
gap-lock behavior. Before relying on the concurrency guarantees, run an
integration test with two independent MySQL sessions that race creation against
acceptance or direct member addition for the same organization and recipient,
and race acceptance against revocation and rejection.

Concurrent token rotations can also deliver invitation emails out of order:
an earlier SMTP send can be delayed until after a later request rotates the
token, making the earlier email's link invalid. The current synchronous SMTP
implementation does not guarantee delivery order. The minimal robust follow-up
would be a transactional outbox and dispatcher that checks the invitation's
current token generation/hash before sending; that requires additional schema
and dispatch infrastructure and is not implemented here.

If the database connection fails during `COMMIT`, its outcome can be uncertain:
the server may have committed even though the application did not receive the
confirmation. The request propagates an error and does not send the token; a
subsequent rollback only cleans up the local session and cannot prove the
server-side transaction was undone. Avoiding this uncertainty safely, while
also preventing an old token from invalidating a token whose email has already
been sent, requires a transactional outbox and delivery state/generation. That
requires schema and dispatcher work and is not implemented here.

## Configuration

Set these environment variables in the deployment environment or the ignored
`backend/.env` file:

- `EMAIL_PROVIDER` (currently supported value: `smtp`)
- `APP_ENV` (defaults to `production`; set `development`, `dev`, or `local`
  explicitly for local development)
- `SMTP_HOST`
- `SMTP_PORT` (defaults to `587`)
- `SMTP_USERNAME` and `SMTP_PASSWORD` (both optional for unauthenticated SMTP;
  configure both when authentication is required)
- `SMTP_FROM`
- `SMTP_STARTTLS` (defaults to `true` and must remain enabled)
- `APP_BASE_URL` (public frontend base URL used to build invitation links)

Invitation links require HTTPS except for `http://localhost`,
`http://127.0.0.1`, or `http://[::1]` when `APP_ENV` is `development`, `dev`,
or `local`. `APP_ENV` defaults to `production`, so omitting it cannot enable
the local HTTP exception; developers who use HTTP loopback must explicitly set
`APP_ENV=development` (or `dev`/`local`). HTTPS remains required for external
URLs. The mailer supports SMTP with STARTTLS, using port 587 by default;
credentials are only sent after STARTTLS has been established. STARTTLS is
required for all SMTP delivery, including unauthenticated relay; disabling it
prevents invitation emails from being sent. An unauthenticated SMTP relay is
supported only when it offers STARTTLS. There is no separate unencrypted
local-mail mode. Implicit TLS (`SMTP_SSL`, often used on port 465) is not
currently supported; configure a provider endpoint and port that support
STARTTLS.

Do not put real credentials in version-controlled files.

## Schema and rollout

The invitation model now distinguishes rejection from administrative
revocation with nullable `rejected_at`. Apply the unapplied Alembic revision
`9d6f48c2a13b` before deploying this model change. The migration has not been
run as part of this implementation.

Existing rows with `revoked_at` cannot be reliably classified as prior
recipient rejections or administrative revocations. They will be reported as
revoked; no historical backfill is attempted.
