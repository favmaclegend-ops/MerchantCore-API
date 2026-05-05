import logging
import smtplib
from email.mime.text import MIMEText

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

    msg = MIMEText(html_content, "html")
    msg["Subject"] = "Verify Your Email Address"
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    msg["To"] = email

    try:
        logger.info(f"Connecting to SMTP server: {settings.SMTP_HOST}:{settings.SMTP_PORT}")
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
            server.starttls()
            logger.info(f"Logging in as {settings.SMTP_USER}")
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_FROM_EMAIL, email, msg.as_string())
            logger.info(f"Email sent successfully to {email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {email}: {e}")
        return False
