import logging

import resend
from app.config import settings

logger = logging.getLogger(__name__)


def send_verification_email(email: str, token: str) -> bool:
    logger.info(f"Sending verification email to {email}")
    base_url = settings.PUBLIC_URL or "https://merchantcore-api.onrender.com"
    verification_link = f"{base_url}/api/v1/auth/verify-email?token={token}"
    html_content = f"""\
<html>
<body>
<p>Hi,</p>
<p>Thank you for registering. Please click the link below to verify your email address:</p>
<p><a href="{verification_link}">Verify Email</a></p>
<p>This link will expire in {settings.TOKEN_EXPIRE_MINUTES} minutes.</p>
<p>If you did not create an account, please ignore this email.</p>
</body>
</html>
"""

    if not settings.RESEND_API_KEY:
        logger.error("RESEND_API_KEY not set")
        return False

    resend.api_key = settings.RESEND_API_KEY

    try:
        response = resend.Emails.send({
            "from": f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>",
            "to": [email],
            "subject": "Verify Your Email Address",
            "html": html_content,
        })
        logger.info(f"Email sent successfully to {email}: {response}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {email}: {e}")
        return False
