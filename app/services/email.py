import logging
from typing import Optional

import yagmail

from app.config import settings

logger = logging.getLogger(__name__)


class EmailNotConfiguredError(RuntimeError):
    """Raised when no email provider (SMTP or Resend) is configured."""


def email_provider_configured() -> bool:
    return bool(settings.SMTP_USER and settings.SMTP_PASSWORD) or bool(settings.RESEND_API_KEY)


def _missing_settings() -> str:
    missing = []
    if not (settings.SMTP_USER and settings.SMTP_PASSWORD) and not settings.RESEND_API_KEY:
        missing.append("RESEND_API_KEY, or SMTP_USER + SMTP_PASSWORD (with SMTP_HOST/SMTP_FROM_EMAIL)")
    return "; ".join(missing)


def _send_via_smtp(to_email: str, subject: str, html: str) -> bool:
    """Send through SMTP (e.g. Gmail app password) using yagmail."""
    try:
        yag = yagmail.SMTP(
            user=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            host=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            smtp_starttls=True,
            smtp_ssl=False,
        )
        yag.send(
            to=to_email,
            subject=subject,
            contents=html,
            headers={"From": f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"},
        )
        logger.info("Email sent successfully to %s via SMTP", to_email)
        return True
    except Exception as e:
        logger.error("Failed to send email to %s via SMTP: %s", to_email, e)
        raise RuntimeError(
            f"SMTP failed to send verification email to {to_email}: {e}. "
            f"Check SMTP_HOST={settings.SMTP_HOST!r}, SMTP_PORT={settings.SMTP_PORT}, "
            f"SMTP_USER={settings.SMTP_USER!r}, SMTP_PASSWORD length and SMTP_FROM_EMAIL={settings.SMTP_FROM_EMAIL!r}."
        ) from e


def send_email(to_email: str, subject: str, html: str) -> bool:
    """Send an email via the configured provider (Resend or SMTP).

    Fails loudly instead of swallowing errors: raises ``EmailNotConfiguredError``
    when no provider is configured, and re-raises provider failures with the
    underlying cause, so callers/endpoints can surface a clear message.
    """
    if email_provider_configured():
        if settings.RESEND_API_KEY:
            try:
                import resend

                resend.api_key = settings.RESEND_API_KEY
                response = resend.Emails.send({
                    "from": f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>",
                    "to": [to_email],
                    "subject": subject,
                    "html": html,
                })
                logger.info("Email sent successfully to %s via Resend: %s", to_email, response)
                return True
            except Exception as e:
                logger.error("Failed to send email to %s via Resend: %s", to_email, e)
                raise RuntimeError(
                    f"Resend failed to send verification email to {to_email}: {e}. "
                    f"Check RESEND_API_KEY and SMTP_FROM_EMAIL={settings.SMTP_FROM_EMAIL!r}."
                ) from e

        # SMTP configured (Resend key absent)
        return _send_via_smtp(to_email, subject, html)

    raise EmailNotConfiguredError(
        "Cannot send verification email: no email provider is configured. "
        f"Set one of the following environment variables on Render: {_missing_settings()}. "
        "Until configured, verification codes cannot be delivered."
    )


def send_verification_email(email: str, otp: str, raise_on_error: bool = True) -> Optional[bool]:
    logger.info("Sending verification email to %s", email)
    html_content = f"""\
<html>
<body>
<p>Hi,</p>
<p>Thank you for registering. Your verification code is:</p>
<h2 style="letter-spacing: 8px; font-size: 32px; text-align: center;">{otp}</h2>
<p>Enter this code in the app to verify your email address.</p>
<p>This code will expire in 15 minutes.</p>
<p>If you did not create an account, please ignore this email.</p>
</body>
</html>
"""
    try:
        return send_email(to_email=email, subject="Your Verification Code", html=html_content)
    except Exception:
        if raise_on_error:
            raise
        logger.exception("Verification email to %s failed", email)
        return False
