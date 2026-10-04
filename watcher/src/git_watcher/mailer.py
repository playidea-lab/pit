"""SMTP 발송 (평문 + HTML + 첨부)."""

import mimetypes
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

from git_watcher.config import Settings


def send_mail(settings: Settings, subject: str, text: str, html: str, attachments: tuple[Path, ...] = ()) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.mail_from or settings.smtp_user
    msg["To"] = ", ".join(settings.mail_to)
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    for path in attachments:
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        maintype, subtype = mime.split("/", 1)
        msg.add_attachment(path.read_bytes(), maintype=maintype, subtype=subtype, filename=path.name)
    with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=ssl.create_default_context()) as smtp:
        smtp.login(settings.smtp_user, settings.smtp_password.get_secret_value())
        smtp.send_message(msg)
