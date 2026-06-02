"""
Async Kafka consumer — subscribes to go.alerts and dispatches notifications.

Runs as a long-lived asyncio background task alongside the poll loop.
Each consumed alert represents a train that crossed the delay threshold
and is actively getting worse.

Extend _handle_alert() to fan-out to registered user subscriptions
(email, WhatsApp) once Phase 3b (user subscriptions) is implemented.
"""
import asyncio
import json

import structlog
from aiokafka import AIOKafkaConsumer

from config import KAFKA_BOOTSTRAP_SERVERS, KAFKA_ENABLED
from kafka import TOPIC_ALERTS

log = structlog.get_logger(__name__)


async def _handle_alert(alert: dict) -> None:
    """
    Process one alert event from the go.alerts topic.

    Currently: structured log only.
    Phase 3b hook: look up subscribers for alert["route_id"] and notify them.
    """
    log.warning(
        "KAFKA_ALERT_RECEIVED",
        trip_id=alert.get("trip_id"),
        route_id=alert.get("route_id"),
        delay_s=alert.get("current_delay_s"),
        delta_s=alert.get("delta_s"),
        trend=alert.get("trend"),
        message=alert.get("message"),
    )
    # Phase 3b:  await subscriber_registry.notify(alert)


async def run_alert_consumer() -> None:
    """
    Long-running consumer loop. Start as an asyncio.Task in main.py.
    Exits cleanly when the task is cancelled (e.g. on Ctrl+C).
    """
    if not KAFKA_ENABLED:
        return

    consumer = AIOKafkaConsumer(
        TOPIC_ALERTS,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id="go-alert-dispatcher",
        auto_offset_reset="latest",
        value_deserializer=lambda raw: json.loads(raw.decode("utf-8")),
    )
    await consumer.start()
    log.info("kafka_consumer_started", topic=TOPIC_ALERTS, group="go-alert-dispatcher")

    try:
        async for msg in consumer:
            try:
                await _handle_alert(msg.value)
            except Exception as exc:
                log.error("alert_handler_error", error=str(exc), value=msg.value)
    except asyncio.CancelledError:
        log.info("kafka_consumer_cancelled")
    finally:
        await consumer.stop()
        log.info("kafka_consumer_stopped")
