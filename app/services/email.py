import logging

import yagmail

from app.config import settings

logger = logging.getLogger(__name__)


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
        return False


def send_email(to_email: str, subject: str, html: str) -> bool:
    """Send an email. Uses SMTP (yagmail) when configured, else Resend, else logs to console.

    In development (no SMTP credentials and no ``RESEND_API_KEY``) the message —
    including any OTP code — is printed to the server console so the verify flow
    stays usable without an email service.
    """
    if settings.SMTP_USER and settings.SMTP_PASSWORD:
        return _send_via_smtp(to_email, subject, html)

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
            return False

    logger.error("No SMTP or RESEND_API_KEY configured")
    print(f"[dev-email] To: {to_email} | Subject: {subject}\n{html}", flush=True)
    return False


def send_verification_email(email: str, otp: str) -> bool:
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
    return send_email(to_email=email, subject="Your Verification Code", html=html_content)
