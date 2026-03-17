import smtplib
from email.mime.text import MIMEText
from app.core.config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS

def send_email(to_email: str, subject: str, body: str):
    msg = MIMEText(body, "html")
    msg["Subject"] = subject
    msg["From"] = SMTP_USER
    msg["To"] = to_email

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, to_email, msg.as_string())
