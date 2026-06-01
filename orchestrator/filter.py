"""
Filters raw GTFS-RT data down to trips/vehicles relevant to us:
  - Route: Lakeshore West only
  - Station: stop updates that include Oakville GO
"""
from typing import List
from config import LAKESHORE_WEST_ROUTE_SUFFIX, OAKVILLE_STOP_ID
from ingestor.models import TripUpdate, VehiclePosition, StopTimeUpdate


def filter_lakeshore_west_trips(trip_updates: List[TripUpdate]) -> List[TripUpdate]:
    """
    Keep only Lakeshore West trip updates.
    route_id format: '{date}-LW' where date rotates daily — match by suffix.
    """
    return [tu for tu in trip_updates if tu.route_id.endswith(LAKESHORE_WEST_ROUTE_SUFFIX)]


def filter_vehicles_on_lakeshore_west(vehicles: List[VehiclePosition]) -> List[VehiclePosition]:
    """Keep only vehicles on Lakeshore West."""
    return [v for v in vehicles if v.route_id.endswith(LAKESHORE_WEST_ROUTE_SUFFIX)]


def get_oakville_stop_update(trip_update: TripUpdate) -> StopTimeUpdate | None:
    """
    Return the StopTimeUpdate for Oakville GO within a trip, or None if not present.
    Uses stop_id prefix match because Metrolinx stop_ids may have direction suffixes.
    """
    for stu in trip_update.stop_time_updates:
        if stu.stop_id.startswith(OAKVILLE_STOP_ID):
            return stu
    return None


def get_representative_delay(trip_update: TripUpdate) -> int | None:
    """
    Return the best single delay figure (seconds) for a trip:
    1. Oakville stop update (preferred)
    2. First stop update with any delay value
    3. None if no delay info at all
    """
    oakville = get_oakville_stop_update(trip_update)
    if oakville is not None:
        return oakville.arrival_delay or oakville.departure_delay

    for stu in trip_update.stop_time_updates:
        if stu.arrival_delay is not None:
            return stu.arrival_delay
        if stu.departure_delay is not None:
            return stu.departure_delay

    return None
