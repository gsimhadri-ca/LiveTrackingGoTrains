"""
Fetches and parses GTFS-Realtime Protobuf feeds from Metrolinx.

Responsibilities:
  - Async HTTP polling via httpx
  - Protobuf → Python dataclass conversion
  - Structured logging of fetch latency and parse errors
"""
import time
import structlog
import httpx
from google.transit import gtfs_realtime_pb2
from typing import List, Tuple

from config import METROLINX_API_KEY, GTFS_TRIP_UPDATES_URL, GTFS_VEHICLE_POSITIONS_URL
from ingestor.models import TripUpdate, VehiclePosition, StopTimeUpdate

log = structlog.get_logger(__name__)

# Metrolinx GTFS-RT feeds authenticate via query param ?key=...
_AUTH_PARAMS = {"key": METROLINX_API_KEY}


async def fetch_raw(client: httpx.AsyncClient, url: str) -> bytes:
    """Fetch raw protobuf bytes and log latency."""
    t0 = time.monotonic()
    response = await client.get(url, params=_AUTH_PARAMS, timeout=15.0)
    latency_ms = (time.monotonic() - t0) * 1000
    response.raise_for_status()
    log.info("feed_fetched", url=url, status=response.status_code, latency_ms=round(latency_ms, 1))
    return response.content


def _parse_trip_updates(raw: bytes) -> List[TripUpdate]:
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(raw)

    result: List[TripUpdate] = []
    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue
        tu = entity.trip_update
        trip = tu.trip

        stop_updates = []
        for stu in tu.stop_time_update:
            stop_updates.append(StopTimeUpdate(
                stop_id=stu.stop_id,
                stop_sequence=stu.stop_sequence,
                arrival_delay=stu.arrival.delay if stu.HasField("arrival") else None,
                departure_delay=stu.departure.delay if stu.HasField("departure") else None,
            ))

        result.append(TripUpdate(
            trip_id=trip.trip_id,
            route_id=trip.route_id,
            direction_id=trip.direction_id if trip.HasField("direction_id") else None,
            start_date=trip.start_date or None,
            stop_time_updates=stop_updates,
        ))

    log.debug("parsed_trip_updates", count=len(result))
    return result


def _parse_vehicle_positions_json(raw: bytes) -> List[VehiclePosition]:
    """
    Vehicle positions endpoint returns JSON (GTFS-RT JSON encoding), not Protobuf.
    Structure: {"header": {...}, "entity": [{"id": ..., "vehicle": {...}}, ...]}
    """
    import json
    data = json.loads(raw)
    result: List[VehiclePosition] = []

    for entity in data.get("entity", []):
        v = entity.get("vehicle")
        if not v:
            continue
        trip = v.get("trip", {})
        pos = v.get("position", {})
        vehicle_meta = v.get("vehicle", {})

        result.append(VehiclePosition(
            trip_id=trip.get("trip_id", ""),
            route_id=trip.get("route_id", ""),
            vehicle_label=vehicle_meta.get("label") or None,
            latitude=pos.get("latitude"),
            longitude=pos.get("longitude"),
            current_stop_sequence=v.get("current_stop_sequence"),
            current_status=v.get("current_status"),
        ))

    log.debug("parsed_vehicle_positions", count=len(result))
    return result


async def fetch_trip_updates(client: httpx.AsyncClient) -> List[TripUpdate]:
    try:
        raw = await fetch_raw(client, GTFS_TRIP_UPDATES_URL)
        return _parse_trip_updates(raw)
    except Exception as exc:
        log.error("trip_update_fetch_failed", error=str(exc))
        return []


async def fetch_vehicle_positions(client: httpx.AsyncClient) -> List[VehiclePosition]:
    try:
        raw = await fetch_raw(client, GTFS_VEHICLE_POSITIONS_URL)
        return _parse_vehicle_positions_json(raw)
    except Exception as exc:
        log.error("vehicle_position_fetch_failed", error=str(exc))
        return []


async def fetch_all(client: httpx.AsyncClient) -> Tuple[List[TripUpdate], List[VehiclePosition]]:
    """Fetch both feeds concurrently."""
    import asyncio
    trip_updates, vehicle_positions = await asyncio.gather(
        fetch_trip_updates(client),
        fetch_vehicle_positions(client),
    )
    return trip_updates, vehicle_positions
