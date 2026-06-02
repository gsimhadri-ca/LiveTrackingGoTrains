"""
One-shot snapshot: prints all Lakeshore West trains with their current delay.

Usage:
    venv\Scripts\python show_delays.py

No loop — fetches once and exits.
"""
import asyncio
import sys
import httpx
import structlog
import logging

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    processors=[
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ],
)

import config
from ingestor.fetcher import fetch_trip_updates
from orchestrator.filter import (
    filter_lakeshore_west_trips,
    get_representative_delay,
    get_oakville_stop_update,
)


def _fmt(seconds: int) -> str:
    sign = "+" if seconds >= 0 else "-"
    m, s = divmod(abs(seconds), 60)
    return f"{sign}{m}m {s:02d}s"


async def main() -> None:
    async with httpx.AsyncClient() as client:
        trip_updates = await fetch_trip_updates(client)

    lw = filter_lakeshore_west_trips(trip_updates)
    print(f"\n{'='*62}")
    print(f"  Lakeshore West  —  {len(lw)} trips in live feed")
    print(f"{'='*62}")

    rows = []
    for tu in lw:
        delay = get_representative_delay(tu)
        if delay is None:
            continue
        oa_stu = get_oakville_stop_update(tu)
        oa_delay = None
        if oa_stu:
            oa_delay = oa_stu.arrival_delay or oa_stu.departure_delay
        rows.append((delay, tu.trip_id, tu.route_id, oa_delay))

    # Sort: most delayed first
    rows.sort(key=lambda r: r[0], reverse=True)

    on_time = [r for r in rows if r[0] < 60]
    delayed = [r for r in rows if r[0] >= 60]
    no_data = len(lw) - len(rows)

    # ── Delayed trains ────────────────────────────────────────────────
    print(f"\n  DELAYED  ({len(delayed)} trains, ≥1 min late)\n")
    if delayed:
        print(f"  {'DELAY':>8}  {'OAK DELAY':>10}  TRIP ID")
        print(f"  {'-'*8}  {'-'*10}  {'-'*28}")
        for delay, trip_id, route_id, oa_delay in delayed:
            oa_str = _fmt(oa_delay) if oa_delay is not None else "   n/a"
            flag = "  ⚠" if delay >= 300 else ""
            print(f"  {_fmt(delay):>8}  {oa_str:>10}  {trip_id}{flag}")
    else:
        print("  No trains delayed ≥1 min right now.")

    # ── On-time / early trains ────────────────────────────────────────
    print(f"\n  ON TIME / EARLY  ({len(on_time)} trains)")
    if on_time:
        print(f"  {'DELAY':>8}  TRIP ID")
        print(f"  {'-'*8}  {'-'*28}")
        for delay, trip_id, route_id, _ in on_time:
            print(f"  {_fmt(delay):>8}  {trip_id}")

    if no_data:
        print(f"\n  {no_data} trip(s) had no delay data in this snapshot.")

    print(f"\n  ⚠  = delay ≥5 min (alert threshold)")
    print(f"  OAK DELAY = delay specifically at Oakville GO stop\n")


if __name__ == "__main__":
    asyncio.run(main())
