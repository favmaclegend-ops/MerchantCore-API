import logging

import resend

from app.config import settings

logger = logging.getLogger(__name__)


def send_email(to_email: str, subject: str, html: str) -> bool:
    """Send an email through Resend. Returns False when the API key is missing.

    In development (no ``RESEND_API_KEY``) the message — including any OTP code — is
    printed to the server console so the verify flow stays usable without an email service.
    """
    if not settings.RESEND_API_KEY:
        logger.error("RESEND_API_KEY not set")
        print(f"[dev-email] To: {to_email} | Subject: {subject}\n{html}", flush=True)
        return False

    resend.api_key = settings.RESEND_API_KEY
    try:
        response = resend.Emails.send({
            "from": f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>",
            "to": [to_email],
            "subject": subject,
            "html": html,
        })
        logger.info(f"Email sent successfully to {to_email}: {response}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return False


def send_verification_email(email: str, otp: str) -> bool:
    logger.info(f"Sending verification email to {email}")
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
