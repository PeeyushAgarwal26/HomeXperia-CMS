import aiosmtplib
from email.message import EmailMessage

from app.core.config import settings


async def send_email(to: str, subject: str, body_html: str) -> None:
    message = EmailMessage()
    message["From"] = f"{settings.smtp_from_name} <{settings.smtp_username}>"
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body_html, subtype="html")

    await aiosmtplib.send(
        message,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username,
        password=settings.smtp_password,
        start_tls=True,
    )
