import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import urlencode, urlsplit

from app import config


class EmailDeliveryError(RuntimeError):
    pass


def build_invitation_url(invitation_id: int, token: str) -> str:
    if not config.APP_BASE_URL:
        raise EmailDeliveryError("Invitation email configuration is incomplete.")

    base_url = config.APP_BASE_URL.rstrip("/")
    try:
        parsed_url = urlsplit(base_url)
        is_local_http = (
            config.APP_ENV in {"development", "dev", "local"}
            and parsed_url.scheme == "http"
            and parsed_url.hostname in {"localhost", "127.0.0.1", "::1"}
        )
        is_invalid = (
            not parsed_url.hostname
            or parsed_url.username is not None
            or parsed_url.password is not None
            or parsed_url.query
            or parsed_url.fragment
            or (parsed_url.scheme != "https" and not is_local_http)
        )
    except ValueError:
        is_invalid = True

    if is_invalid:
        raise EmailDeliveryError("Invitation email configuration is invalid.")

    query = urlencode({"invitation_id": invitation_id, "token": token})
    return f"{base_url}/invitations/accept?{query}"


def send_invitation_email(
    *,
    recipient: str,
    organization_name: str,
    role: str,
    expires_at: str,
    invitation_url: str,
) -> None:
    if (
        config.EMAIL_PROVIDER != "smtp"
        or not config.SMTP_HOST
        or not config.SMTP_FROM
        or (config.SMTP_USERNAME and not config.SMTP_PASSWORD)
        or (config.SMTP_PASSWORD and not config.SMTP_USERNAME)
    ):
        raise EmailDeliveryError("Invitation email configuration is incomplete.")
    if not config.SMTP_STARTTLS:
        raise EmailDeliveryError(
            "SMTP STARTTLS is required for invitation email delivery."
        )

    try:
        message = EmailMessage()
        message["Subject"] = f"Invitación a {organization_name} en DevTrack"
        message["From"] = config.SMTP_FROM
        message["To"] = recipient
        message.set_content(
            f"Has sido invitado a la organización {organization_name} "
            f"con el rol {role}.\n"
            f"La invitación caduca el {expires_at}.\n\n"
            f"Acepta la invitación: {invitation_url}\n"
        )

        with smtplib.SMTP(
            config.SMTP_HOST,
            config.SMTP_PORT,
            timeout=15,
        ) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            if config.SMTP_USERNAME:
                smtp.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException, ValueError) as exc:
        raise EmailDeliveryError("Invitation email delivery failed.") from exc
