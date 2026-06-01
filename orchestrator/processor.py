"""
Core processing loop:
  1. Receives parsed GTFS-RT data from the ingestor
  2. Filters to Lakeshore West / Oakville
  3. Computes delay delta via state store
  4. Fires alert events to the notifier when threshold is crossed
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
from notifier.notifier import dispatch_alert

log = structlog.get_logger(__name__)


def process(trip_updates: List[TripUpdate], vehicles: List[VehiclePosition]) -> None:
    """
    Called every poll cycle with fresh data.
    Mutates in-memory state and fires alerts as a side effect.
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
            continue  # no delay info for this trip yet

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

        # Alert condition: delay is above threshold AND worsening since last poll
        if current_delay >= DELAY_THRESHOLD_SECONDS and trend == "WORSENING":
            dispatch_alert(
                trip_id=trip.trip_id,
                route_id=trip.route_id,
                current_delay=current_delay,
                delta=delta,
                trend=trend,
                oakville_stop=oakville_stu,
            )

    # Evict state entries for trips that haven't been seen in 1 hour
    evicted = state.evict_stale(max_age_seconds=3600)
    if evicted:
        log.debug("state_evicted", count=evicted)
