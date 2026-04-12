import resend
import os

resend.api_key = os.getenv("RESEND_API_KEY", "")

def send_email(to_email: str, subject: str, body: str):
    if not resend.api_key:
        raise RuntimeError("RESEND_API_KEY is not configured")

    params = {
        "from": "CENRO EMC System <noreply@gmail.com>",
        "to":   [to_email],
        "subject": subject,
        "html": body,
    }
    r = resend.Emails.send(params)
    print(f"[Email] Sent via Resend: {r}")