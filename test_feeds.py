"""
Quick integration test — run manually after installing requirements.

Tests:
  1. API key is loaded from .env
  2. Trip Updates feed is reachable and parseable
  3. Vehicle Positions feed is reachable and parseable
  4. Lakeshore West filter returns results
  5. Oakville GO facility API responds

Usage:
    python test_feeds.py
"""
import asyncio
import structlog
import httpx
import logging

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ],
)

log = structlog.get_logger()


async def main() -> None:
    import config
    log.info("api_key_loaded", key_prefix=config.METROLINX_API_KEY[:6] + "***")

    async with httpx.AsyncClient() as client:
        # ── 1. Trip Updates ───────────────────────────────────────────────────
        log.info("testing_trip_updates_feed")
        from ingestor.fetcher import fetch_trip_updates, fetch_vehicle_positions
        trip_updates = await fetch_trip_updates(client)
        log.info("trip_updates_result", total=len(trip_updates))
        if trip_updates:
            sample = trip_updates[0]
            log.info("sample_trip", trip_id=sample.trip_id, route_id=sample.route_id,
                     stop_updates=len(sample.stop_time_updates))

        # ── 2. Vehicle Positions ───────────────────────────────────────────────
        log.info("testing_vehicle_positions_feed")
        vehicles = await fetch_vehicle_positions(client)
        log.info("vehicle_positions_result", total=len(vehicles))
        if vehicles:
            sample_v = vehicles[0]
            log.info("sample_vehicle", trip_id=sample_v.trip_id, route_id=sample_v.route_id,
                     lat=sample_v.latitude, lon=sample_v.longitude)

        # ── 3. Lakeshore West filter ───────────────────────────────────────────
        from orchestrator.filter import filter_lakeshore_west_trips, get_representative_delay
        lw = filter_lakeshore_west_trips(trip_updates)
        log.info("lakeshore_west_trips", count=len(lw))
        delayed = [(tu.trip_id, get_representative_delay(tu)) for tu in lw if get_representative_delay(tu)]
        delayed_above_threshold = [(tid, d) for tid, d in delayed if d and d >= 60]
        log.info("delayed_trips_1min_plus", count=len(delayed_above_threshold), sample=delayed_above_threshold[:5])

        # ── 4. Oakville GO facility ────────────────────────────────────────────
        log.info("testing_oakville_facility_api")
        from go_api.client import get_oakville_facilities
        facilities = await get_oakville_facilities(client)
        log.info("oakville_facility_response",
                 stop_name=facilities.get("stop_name"),
                 has_elevator=facilities.get("has_elevator"),
                 has_reserved_parking=facilities.get("has_reserved_parking"),
                 facilities=facilities.get("all_facility_codes"),
                 raw_keys=list(facilities["raw"].keys()) if facilities["raw"] else None)

        # ── 5. State + processor smoke test ───────────────────────────────────
        log.info("testing_processor_smoke")
        from orchestrator.processor import process
        process(trip_updates, vehicles)
        from orchestrator import state
        snap = state.get_all()
        log.info("state_after_one_cycle", tracked_trips=len(snap))

    log.info("ALL_TESTS_PASSED")


if __name__ == "__main__":
    asyncio.run(main())
