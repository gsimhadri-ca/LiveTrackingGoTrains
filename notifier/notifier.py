"""
Alert dispatcher — decoupled from the orchestrator.

Currently: structured-log output only (easy to read, easy to extend).
Future hooks:
  - WhatsApp (reuse Temple bot pattern)
  - SMS via Twilio
  - Push to a dashboard websocket

To add a new channel: implement a function matching the signature
    async def _send_<channel>(alert: dict) -> None
and add it to ENABLED_CHANNELS at the bottom.
"""
import structlog
from typing import Optional
from ingestor.models import StopTimeUpdate

log = structlog.get_logger(__name__)


def _format_delay(seconds: int) -> str:
    minutes, secs = divmod(abs(seconds), 60)
    sign = "+" if seconds >= 0 else "-"
    return f"{sign}{minutes}m {secs:02d}s"


def _build_alert(
    trip_id: str,
    route_id: str,
    current_delay: int,
    delta: int,
    trend: str,
    oakville_stop: Optional[StopTimeUpdate],
) -> dict:
    alert = {
        "trip_id": trip_id,
        "route_id": route_id,
        "current_delay_human": _format_delay(current_delay),
        "delta_human": _format_delay(delta),
        "trend": trend,
        "message": (
            f"GO Train {trip_id} (Route {route_id}) is now "
            f"{_format_delay(current_delay)} late and {trend} "
            f"(grew by {_format_delay(delta)} since last poll)."
        ),
    }

    if oakville_stop:
        oakville_delay = oakville_stop.arrival_delay or oakville_stop.departure_delay
        if oakville_delay is not None:
            alert["oakville_delay_human"] = _format_delay(oakville_delay)
            alert["message"] += f" Expected delay at Oakville GO: {_format_delay(oakville_delay)}."

    return alert


def _log_alert(alert: dict) -> None:
    """Default channel: structured log at WARNING level."""
    log.warning(
        "DELAY_ALERT",
        trip_id=alert["trip_id"],
        route_id=alert["route_id"],
        current_delay=alert["current_delay_human"],
        delta=alert["delta_human"],
        trend=alert["trend"],
        message=alert["message"],
        oakville_delay=alert.get("oakville_delay_human", "n/a"),
    )


# ── Public API ────────────────────────────────────────────────────────────────

def dispatch_alert(
    trip_id: str,
    route_id: str,
    current_delay: int,
    delta: int,
    trend: str,
    oakville_stop: Optional[StopTimeUpdate] = None,
) -> None:
    """Build and dispatch an alert through all enabled channels."""
    alert = _build_alert(trip_id, route_id, current_delay, delta, trend, oakville_stop)
    for channel_fn in _ENABLED_CHANNELS:
        try:
            channel_fn(alert)
        except Exception as exc:
            log.error("alert_channel_failed", channel=channel_fn.__name__, error=str(exc))


# Add / remove channels here — order determines dispatch order
_ENABLED_CHANNELS = [
    _log_alert,
    # _whatsapp_alert,   # uncomment when implemented
    # _sms_alert,        # uncomment when implemented
]
