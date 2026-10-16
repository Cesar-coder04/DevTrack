from email import message_from_string
from email.policy import default
from smtplib import SMTPAuthenticationError

import pytest

from app.services import email_service


class FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.tls_context = None
        self.credentials = None
        self.message = None
        self.__class__.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def starttls(self, context):
        self.tls_context = context

    def login(self, username, password):
        self.credentials = (username, password)

    def send_message(self, message):
        self.message = message


def configure_smtp(monkeypatch):
    monkeypatch.setattr(email_service.config, "EMAIL_PROVIDER", "smtp")
    monkeypatch.setattr(email_service.config, "SMTP_HOST", "smtp.test")
    monkeypatch.setattr(email_service.config, "SMTP_PORT", 587)
    monkeypatch.setattr(email_service.config, "SMTP_USERNAME", "mailer")
    monkeypatch.setattr(email_service.config, "SMTP_PASSWORD", "do-not-log-this")
    monkeypatch.setattr(email_service.config, "SMTP_FROM", "noreply@example.test")
    monkeypatch.setattr(email_service.config, "SMTP_STARTTLS", True)
    monkeypatch.setattr(email_service.config, "APP_BASE_URL", "https://app.test")
    monkeypatch.setattr(email_service.smtplib, "SMTP", FakeSMTP)
    FakeSMTP.instances.clear()


def test_invitation_email_contains_invitation_details_and_uses_starttls(monkeypatch):
    configure_smtp(monkeypatch)
    invitation_url = email_service.build_invitation_url(
        9, "secret-token-that-must-not-be-in-json"
    )

    email_service.send_invitation_email(
        recipient="invitee@example.test",
        organization_name="Acme",
        role="admin",
        expires_at="2026-10-22T12:00:00+00:00",
        invitation_url=invitation_url,
    )

    smtp = FakeSMTP.instances[0]
    assert (smtp.host, smtp.port, smtp.timeout) == ("smtp.test", 587, 15)
    assert smtp.tls_context is not None
    assert smtp.credentials == ("mailer", "do-not-log-this")
    parsed = message_from_string(smtp.message.as_string(), policy=default)
    assert parsed["To"] == "invitee@example.test"
    assert parsed["From"] == "noreply@example.test"
    body = parsed.get_body(preferencelist=("plain",)).get_content()
    assert "Acme" in body
    assert "admin" in body
    assert "2026-10-22T12:00:00+00:00" in body
    assert invitation_url in body
    assert "secret-token-that-must-not-be-in-json" in invitation_url


def test_invitation_email_provider_errors_are_sanitized(monkeypatch):
    configure_smtp(monkeypatch)

    def fail_login(self, username, password):
        raise SMTPAuthenticationError(535, b"do-not-log-this")

    monkeypatch.setattr(FakeSMTP, "login", fail_login)

    with pytest.raises(email_service.EmailDeliveryError) as error:
        email_service.send_invitation_email(
            recipient="invitee@example.test",
            organization_name="Acme",
            role="member",
            expires_at="2026-10-22T12:00:00+00:00",
            invitation_url="https://example.test/invitations/accept?token=secret",
        )

    assert str(error.value) == "Invitation email delivery failed."
    assert "do-not-log-this" not in str(error.value)
    assert "secret" not in str(error.value)


def test_invitation_email_requires_complete_configuration(monkeypatch):
    configure_smtp(monkeypatch)
    monkeypatch.setattr(email_service.config, "SMTP_PASSWORD", None)

    with pytest.raises(
        email_service.EmailDeliveryError,
        match="configuration is incomplete",
    ):
        email_service.send_invitation_email(
            recipient="invitee@example.test",
            organization_name="Acme",
            role="member",
            expires_at="2026-10-22T12:00:00+00:00",
            invitation_url="https://example.test/invitations/accept?token=secret",
        )


def test_invitation_email_rejects_credentials_without_starttls(monkeypatch):
    configure_smtp(monkeypatch)
    monkeypatch.setattr(email_service.config, "SMTP_STARTTLS", False)

    with pytest.raises(
        email_service.EmailDeliveryError,
        match="STARTTLS is required",
    ):
        email_service.send_invitation_email(
            recipient="invitee@example.test",
            organization_name="Acme",
            role="member",
            expires_at="2026-10-22T12:00:00+00:00",
            invitation_url="https://example.test/invitations/accept?token=secret",
        )

    assert FakeSMTP.instances == []


def test_unauthenticated_invitation_email_still_requires_starttls(monkeypatch):
    configure_smtp(monkeypatch)
    monkeypatch.setattr(email_service.config, "SMTP_USERNAME", None)
    monkeypatch.setattr(email_service.config, "SMTP_PASSWORD", None)
    monkeypatch.setattr(email_service.config, "SMTP_STARTTLS", False)

    with pytest.raises(
        email_service.EmailDeliveryError,
        match="STARTTLS is required",
    ):
        email_service.send_invitation_email(
            recipient="invitee@example.test",
            organization_name="Acme",
            role="member",
            expires_at="2026-10-22T12:00:00+00:00",
            invitation_url="https://example.test/invitations/accept?token=secret",
        )

    assert FakeSMTP.instances == []


def test_unauthenticated_invitation_email_uses_starttls(monkeypatch):
    configure_smtp(monkeypatch)
    monkeypatch.setattr(email_service.config, "SMTP_USERNAME", None)
    monkeypatch.setattr(email_service.config, "SMTP_PASSWORD", None)

    email_service.send_invitation_email(
        recipient="invitee@example.test",
        organization_name="Acme",
        role="member",
        expires_at="2026-10-22T12:00:00+00:00",
        invitation_url="https://example.test/invitations/accept?token=secret",
    )

    smtp = FakeSMTP.instances[0]
    assert smtp.tls_context is not None
    assert smtp.credentials is None
    assert smtp.message is not None


def test_invitation_url_rejects_loopback_http_in_production(monkeypatch):
    monkeypatch.setattr(email_service.config, "APP_ENV", "production")
    monkeypatch.setattr(
        email_service.config,
        "APP_BASE_URL",
        "http://localhost:3000",
    )

    with pytest.raises(
        email_service.EmailDeliveryError,
        match="configuration is invalid",
    ):
        email_service.build_invitation_url(9, "secret-token")


def test_invitation_url_allows_https_in_production(monkeypatch):
    monkeypatch.setattr(email_service.config, "APP_ENV", "production")
    monkeypatch.setattr(
        email_service.config,
        "APP_BASE_URL",
        "https://app.example.test",
    )

    assert email_service.build_invitation_url(9, "secret-token").startswith(
        "https://app.example.test/"
    )


def test_invitation_url_allows_loopback_http_in_development(monkeypatch):
    monkeypatch.setattr(email_service.config, "APP_ENV", "development")
    monkeypatch.setattr(
        email_service.config,
        "APP_BASE_URL",
        "http://localhost:3000",
    )
    assert email_service.build_invitation_url(9, "secret-token").startswith(
        "http://localhost:3000/"
    )


def test_invitation_url_rejects_external_http_in_development(monkeypatch):
    monkeypatch.setattr(email_service.config, "APP_ENV", "development")
    monkeypatch.setattr(
        email_service.config,
        "APP_BASE_URL",
        "http://app.example.test",
    )
    with pytest.raises(email_service.EmailDeliveryError):
        email_service.build_invitation_url(9, "secret-token")
