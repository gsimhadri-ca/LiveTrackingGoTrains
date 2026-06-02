"""
Alert delivery for subscriptions.

If SMTP_HOST is configured, sends a real email via aiosmtplib.
Otherwise falls back to a structured log entry — so everything works
in dev without any email setup.
"""
from email.message import EmailMessage

import structlog

from config import SMTP_ENABLED, SMTP_FROM, SMTP_HOST, SMTP_PASSWORD, SMTP_PORT, SMTP_USER
from subscriptions.models import Subscription

log = structlog.get_logger(__name__)


def _build_email(sub: Subscription, alert: dict) -> EmailMessage:
    route_id = alert.get("route_id", "")
    delay_s = alert.get("current_delay_s", 0)
    message = alert.get("message", "")
    delay_m = delay_s // 60

    msg = EmailMessage()
    msg["From"] = SMTP_FROM
    msg["To"] = sub.email
    msg["Subject"] = f"GO Transit Alert: {route_id} delayed {delay_m}m"
    msg.set_content(
        f"GO Transit Delay Alert\n\n"
        f"{message}\n\n"
        f"---\n"
        f"You are subscribed to alerts for the {sub.route_suffix} line "
        f"(min delay: {sub.min_delay_minutes}m).\n"
        f"To manage your subscription, visit http://localhost:8000\n"
    )
    return msg


async def notify(sub: Subscription, alert: dict) -> None:
    """Send an alert to one subscriber. No-raises — logs on failure."""
    trip_id = alert.get("trip_id", "")

    if not SMTP_ENABLED:
        log.info(
            "email_alert_logged",
            email=sub.email,
            trip_id=trip_id,
            delay_s=alert.get("current_delay_s"),
            note="SMTP not configured — set SMTP_HOST in .env to send real emails",
        )
        return

    try:
        import aiosmtplib
        email_msg = _build_email(sub, alert)
        await aiosmtplib.send(
            email_msg,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=SMTP_USER or None,
            password=SMTP_PASSWORD or None,
            start_tls=True,
        )
        log.info("email_sent", email=sub.email, trip_id=trip_id)
    except Exception as exc:
        log.error("email_failed", email=sub.email, trip_id=trip_id, error=str(exc))
