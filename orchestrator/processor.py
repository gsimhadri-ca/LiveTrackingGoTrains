"""
Core processing loop:
  1. Receives parsed GTFS-RT data from the ingestor
  2. Filters to Lakeshore West / Oakville
  3. Computes delay delta via Redis state store
  4. Publishes every delay update to Kafka (go.trips.delays)
  5. Fires alert events to the notifier + Kafka (go.alerts) when threshold is crossed
"""
import structlog
from typing import List

from config import DELAY_THRESHOLD_SECONDS
from ingestor.models import TripUpdate, VehiclePosition
from orchestrator.filter import (
    filter_lakeshore_west_trips,
    filter_vehicles_on_lakeshore_west,
    get_representative_delay,
    get_oakville_stop_update,
)
from orchestrator import state
from notifier.notifier import dispatch_alert, format_delay
import kafka.producer as kafka_producer

log = structlog.get_logger(__name__)


async def process(trip_updates: List[TripUpdate], vehicles: List[VehiclePosition]) -> None:
    """
    Called every poll cycle with fresh data.
    Updates Redis state, publishes to Kafka, and fires alerts as side effects.
    """
    lw_trips = filter_lakeshore_west_trips(trip_updates)
    lw_vehicles = filter_vehicles_on_lakeshore_west(vehicles)

    log.info(
        "processing_cycle",
        lakeshore_west_trips=len(lw_trips),
        lakeshore_west_vehicles=len(lw_vehicles),
    )

    for trip in lw_trips:
        current_delay = get_representative_delay(trip)
        if current_delay is None:
            continue

        result = state.update_delay(trip.trip_id, current_delay)
        delta = result["delta"]
        trend = result["trend"]
        oakville_stu = get_oakville_stop_update(trip)

        log.debug(
            "delay_update",
            trip_id=trip.trip_id,
            route_id=trip.route_id,
            current_delay_s=current_delay,
            delta_s=delta,
            trend=trend,
            has_oakville_stop=oakville_stu is not None,
        )

        # Publish every delay update to Kafka (all consumers can filter by trend)
        await kafka_producer.publish_delay(
            trip_id=trip.trip_id,
            route_id=trip.route_id,
            current_delay=current_delay,
            previous_delay=result["previous_delay"],
            delta=delta,
            trend=trend,
        )

        # Alert condition: delay is above threshold AND actively worsening
        if current_delay >= DELAY_THRESHOLD_SECONDS and trend == "WORSENING":
            dispatch_alert(
                trip_id=trip.trip_id,
                route_id=trip.route_id,
                current_delay=current_delay,
                delta=delta,
                trend=trend,
                oakville_stop=oakville_stu,
            )
            await kafka_producer.publish_alert(
                trip_id=trip.trip_id,
                route_id=trip.route_id,
                current_delay=current_delay,
                delta=delta,
                trend=trend,
                message=(
                    f"GO Train {trip.trip_id} (Route {trip.route_id}) is "
                    f"{format_delay(current_delay)} late and WORSENING "
                    f"(grew by {format_delay(delta)} since last poll)."
                ),
            )

    evicted = state.evict_stale(max_age_seconds=3600)
    if evicted:
        log.debug("state_evicted", count=evicted)
