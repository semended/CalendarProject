import smtplib
import sys
from email.message import EmailMessage

from app.config import (
    EMAIL_FROM,
    EMAIL_SMTP_HOST,
    EMAIL_SMTP_PASSWORD,
    EMAIL_SMTP_PORT,
    EMAIL_SMTP_USER,
)


def send_email(to: str, subject: str, body: str) -> None:
    """Отправляет письмо. Если EMAIL_SMTP_HOST не задан — печатает в консоль."""
    if not EMAIL_SMTP_HOST:
        print(
            "\n========== EMAIL (console backend) ==========\n"
            f"To:      {to}\n"
            f"From:    {EMAIL_FROM}\n"
            f"Subject: {subject}\n"
            "---------------------------------------------\n"
            f"{body}\n"
            "=============================================\n",
            file=sys.stderr,
            flush=True,
        )
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = to
    msg.set_content(body)

    with smtplib.SMTP(EMAIL_SMTP_HOST, EMAIL_SMTP_PORT) as s:
        s.starttls()
        if EMAIL_SMTP_USER:
            s.login(EMAIL_SMTP_USER, EMAIL_SMTP_PASSWORD)
        s.send_message(msg)
