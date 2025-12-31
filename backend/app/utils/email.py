import os
import smtplib
from email.message import EmailMessage


def _send_via_resend(to_email: str, subject: str, html: str) -> tuple[bool, str | None]:
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    from_email = os.getenv("RESEND_FROM", "").strip()
    if not api_key or not from_email:
        return False, "Resend not configured"
    try:
        import resend  # type: ignore

        resend.api_key = api_key
        resend.Emails.send(
            {
                "from": from_email,
                "to": to_email,
                "subject": subject,
                "html": html,
            }
        )
        return True, None
    except Exception as exc:
        return False, str(exc)


def _send_via_smtp(to_email: str, subject: str, body: str) -> tuple[bool, str | None]:
    host = os.getenv("SMTP_HOST", "").strip()
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "").strip()
    from_email = os.getenv("SMTP_FROM", "").strip() or username

    if not host or not from_email:
        return False, "SMTP not configured"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email
    msg.set_content(body)

    try:
        with smtplib.SMTP(host, port, timeout=10) as server:
            server.starttls()
            if username and password:
                server.login(username, password)
            server.send_message(msg)
        return True, None
    except Exception as exc:
        return False, str(exc)


def send_email(to_email: str, subject: str, body: str) -> tuple[bool, str | None]:
    html = body if "<" in body else f"<p>{body.replace(chr(10), '<br/>')}</p>"
    ok, error = _send_via_resend(to_email, subject, html)
    if ok:
        return True, None
    return _send_via_smtp(to_email, subject, body)
