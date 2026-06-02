"""
Async Kafka producer for GO Transit delay events.

Topics:
  go.trips.delays — every LW trip delay update (all trends, keyed by trip_id)
  go.alerts       — alert-worthy events only (delay >= threshold AND WORSENING)

Usage:
  await producer.start()        # call once at app startup
  await producer.publish_delay(...)
  await producer.publish_alert(...)
  await producer.stop()         # call on shutdown
"""
import json
from datetime import datetime, timezone
from typing import Optional

import structlog
from aiokafka import AIOKafkaProducer

from config import KAFKA_BOOTSTRAP_SERVERS, KAFKA_ENABLED
from kafka import TOPIC_ALERTS, TOPIC_DELAYS

log = structlog.get_logger(__name__)

_producer: Optional[AIOKafkaProducer] = None


async def start() -> None:
    global _producer
    if not KAFKA_ENABLED:
        log.info("kafka_disabled", reason="KAFKA_ENABLED=false")
        return
    _producer = AIOKafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8") if k else None,
    )
    await _producer.start()
    log.info("kafka_producer_started", bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS)


async def stop() -> None:
    global _producer
    if _producer is not None:
        await _producer.stop()
        _producer = None
        log.info("kafka_producer_stopped")


async def publish_delay(
    trip_id: str,
    route_id: str,
    current_delay: int,
    previous_delay: Optional[int],
    delta: int,
    trend: str,
) -> None:
    """Publish a delay snapshot for one trip. Called for every LW trip each poll cycle."""
    if _producer is None:
        return
    event = {
        "trip_id": trip_id,
        "route_id": route_id,
        "current_delay_s": current_delay,
        "previous_delay_s": previous_delay,
        "delta_s": delta,
        "trend": trend,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await _producer.send(TOPIC_DELAYS, value=event, key=trip_id)


async def publish_alert(
    trip_id: str,
    route_id: str,
    current_delay: int,
    delta: int,
    trend: str,
    message: str,
) -> None:
    """Publish an alert event. Called only when delay >= threshold AND WORSENING."""
    if _producer is None:
        return
    event = {
        "trip_id": trip_id,
        "route_id": route_id,
        "current_delay_s": current_delay,
        "delta_s": delta,
        "trend": trend,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await _producer.send(TOPIC_ALERTS, value=event, key=trip_id)
    log.debug("kafka_alert_published", trip_id=trip_id, delay_s=current_delay)
