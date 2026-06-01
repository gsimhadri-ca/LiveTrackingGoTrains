"""
Entry point — runs the poll loop indefinitely.

Usage:
    python main.py

Press Ctrl+C to stop.
"""
import asyncio
import logging
import structlog
import httpx

import config
from ingestor.fetcher import fetch_all
from orchestrator.processor import process
from go_api.client import get_oakville_facilities


def _configure_logging() -> None:
    log_level = getattr(logging, config.LOG_LEVEL, logging.INFO)
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.dev.ConsoleRenderer(),
        ],
    )


log = structlog.get_logger(__name__)


async def poll_loop() -> None:
    log.info("starting", poll_interval_s=config.POLL_INTERVAL_SECONDS)

    async with httpx.AsyncClient() as client:
        # Fetch Oakville facility state once at startup for context
        facilities = await get_oakville_facilities(client)
        log.info(
            "oakville_go_facilities",
            stop_name=facilities.get("stop_name"),
            has_elevator=facilities.get("has_elevator"),
            has_reserved_parking=facilities.get("has_reserved_parking"),
            ticket_hours=facilities.get("ticket_sales_hours"),
        )

        while True:
            try:
                trip_updates, vehicles = await fetch_all(client)
                process(trip_updates, vehicles)
            except Exception as exc:
                log.error("poll_cycle_error", error=str(exc))

            await asyncio.sleep(config.POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    _configure_logging()
    try:
        asyncio.run(poll_loop())
    except KeyboardInterrupt:
        log.info("stopped_by_user")
