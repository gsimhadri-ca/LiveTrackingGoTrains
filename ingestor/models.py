"""
Pure dataclasses — no external dependencies.
These are the parsed, Python-native representations of GTFS-RT entities.
"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class StopTimeUpdate:
    stop_id: str
    stop_sequence: int
    arrival_delay: Optional[int] = None    # seconds; positive = late
    departure_delay: Optional[int] = None  # seconds; positive = late


@dataclass
class TripUpdate:
    trip_id: str
    route_id: str
    direction_id: Optional[int]            # 0 = inbound, 1 = outbound (GO convention)
    start_date: Optional[str]              # YYYYMMDD
    stop_time_updates: List[StopTimeUpdate] = field(default_factory=list)


@dataclass
class VehiclePosition:
    trip_id: str
    route_id: str
    vehicle_label: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    current_stop_sequence: Optional[int]
    current_status: Optional[str]          # INCOMING_AT | STOPPED_AT | IN_TRANSIT_TO
