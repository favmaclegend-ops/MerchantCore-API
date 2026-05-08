import logging

import resend
from app.config import settings

logger = logging.getLogger(__name__)


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

    if not settings.RESEND_API_KEY:
        logger.error("RESEND_API_KEY not set")
        return False

    resend.api_key = settings.RESEND_API_KEY

    try:
        response = resend.Emails.send({
            "from": f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>",
            "to": [email],
            "subject": "Your Verification Code",
            "html": html_content,
        })
        logger.info(f"Email sent successfully to {email}: {response}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {email}: {e}")
        return False
