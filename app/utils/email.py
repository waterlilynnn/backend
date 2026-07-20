import smtplib
import ssl
from email.mime.text        import MIMEText
from email.mime.multipart   import MIMEMultipart

from app.core.config import SMTP_HOST, SMTP_USER, SMTP_PASS

SMTP_SSL_PORT   = 465
SMTP_TLS_PORT   = 587
CONNECT_TIMEOUT = 15


def _build_message(to_email: str, subject: str, body: str) -> MIMEMultipart:
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"]    = f"CENRO EMC System <{SMTP_USER}>"
    message["To"]      = to_email
    message.attach(MIMEText(body, "html"))
    return message


def _send_via_ssl(to_email: str, message: MIMEMultipart) -> None:
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_SSL_PORT, context=context, timeout=CONNECT_TIMEOUT) as server:
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, to_email, message.as_string())


def _send_via_starttls(to_email: str, message: MIMEMultipart) -> None:
    context = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_TLS_PORT, timeout=CONNECT_TIMEOUT) as server:
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, to_email, message.as_string())


def send_email(to_email: str, subject: str, body: str) -> bool:
    if not SMTP_USER or not SMTP_PASS:
        print("[Email] WARNING: SMTP_USER or SMTP_PASS not set. Email not sent.")
        return False

    message = _build_message(to_email, subject, body)

    try:
        _send_via_ssl(to_email, message)
        print(f"[Email] ✓ Sent to {to_email} via SSL:465 | Subject: {subject}")
        return True

    except smtplib.SMTPAuthenticationError:
        print(
            "[Email] ✗ Gmail authentication failed (SSL:465).\n"
            "  Make sure SMTP_PASS is a Gmail App Password, not your regular password.\n"
            "  Get one at: https://myaccount.google.com/apppasswords"
        )
        return False

    except Exception as e:
        print(f"[Email] ⚠ SSL:465 failed ({e}). Trying STARTTLS:587 fallback…")

    try:
        _send_via_starttls(to_email, message)
        print(f"[Email] ✓ Sent to {to_email} via STARTTLS:587 | Subject: {subject}")
        return True

    except smtplib.SMTPAuthenticationError:
        print(
            "[Email] ✗ Gmail authentication failed (STARTTLS:587).\n"
            "  Make sure SMTP_PASS is a Gmail App Password, not your regular password.\n"
            "  Get one at: https://myaccount.google.com/apppasswords"
        )
        return False

    except smtplib.SMTPException as e:
        print(f"[Email] ✗ SMTP error sending to {to_email}: {e}")
        return False

    except Exception as e:
        print(f"[Email] ✗ Unexpected error sending to {to_email}: {e}")
        return False