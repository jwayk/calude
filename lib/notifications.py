import ssl
import smtplib
from email.message import EmailMessage
from email.utils import formataddr

import _auth
from settings import SMTP


class Emailer:
    def __init__(self):
        self.server = smtplib.SMTP(SMTP["server"], SMTP["port"])
        self.server.starttls(context=ssl.create_default_context())
        self.server.login(_auth.email["username"], _auth.email["password"])

    def _create_message(self, subject: str, recipients: list[str], use_bcc=True):
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = formataddr(("alamovies", _auth.email["username"]))
        message["Bcc" if use_bcc else "To"] = recipients
        return message

    def send_alert(self, error_message: str, recipients: list[str]):
        message = self._create_message(
            subject="Calendar Error", recipients=recipients, use_bcc=False
        )
        message.set_content(error_message)
        self.server.send_message(message)
