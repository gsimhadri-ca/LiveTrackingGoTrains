"""LangChain tools wrapping live Metrolinx APIs."""
import httpx
from langchain_core.tools import tool
from agent import live_mode

_DISABLED_MSG = (
    "Live data is currently disabled. "
    "Turn on the 'Live Data' toggle in the UI to fetch real-time information."
)

from ingestor.fetcher import fetch_trip_updates
from orchestrator.filter import (
    filter_lakeshore_west_trips,
    get_representative_delay,
    get_oakville_stop_update,
)
from go_api.client import get_oakville_facilities as _get_oakville_facilities
from config import METROLINX_API_KEY, GO_API_NEXT_SERVICE_URL, GO_API_EXCEPTIONS_TRAIN_URL


def _fmt_delay(seconds: int) -> str:
    sign = "+" if seconds >= 0 else "-"
    m, s = divmod(abs(seconds), 60)
    return f"{sign}{m}m {s:02d}s"


@tool
async def check_lakeshore_west_delays() -> str:
    """
    Fetch current real-time delays for all Lakeshore West GO trains.
    Returns a sorted summary of delayed trains. Call this whenever the user asks
    about delays, train status, or whether trains are on time.
    """
    if not live_mode.enabled:
        return _DISABLED_MSG
    async with httpx.AsyncClient() as client:
        trips = await fetch_trip_updates(client)

    lw_trips = filter_lakeshore_west_trips(trips)
    if not lw_trips:
        return "No Lakeshore West trains found in the live feed right now."

    results = []
    for trip in lw_trips:
        delay = get_representative_delay(trip)
        if delay is None:
            continue
        oak_stu = get_oakville_stop_update(trip)
        oak_delay = (oak_stu.arrival_delay or oak_stu.departure_delay) if oak_stu else None
        results.append({
            "trip_id": trip.trip_id,
            "delay_s": delay,
            "oakville_delay_s": oak_delay,
        })

    if not results:
        return "All Lakeshore West trains are reporting no delay data."

    results.sort(key=lambda x: x["delay_s"], reverse=True)

    delayed = [r for r in results if r["delay_s"] >= 60]
    on_time = [r for r in results if r["delay_s"] < 60]

    lines = []
    if delayed:
        lines.append(f"Delayed trains ({len(delayed)}):")
        for r in delayed[:10]:
            oak = f" | Oakville stop: {_fmt_delay(r['oakville_delay_s'])}" if r["oakville_delay_s"] is not None else ""
            lines.append(f"  {r['trip_id']}: {_fmt_delay(r['delay_s'])}{oak}")
    else:
        lines.append("No trains delayed by more than 1 minute.")

    lines.append(f"\nOn time / under 1 min delay: {len(on_time)} trains")
    return "\n".join(lines)


@tool
async def get_oakville_station_info() -> str:
    """
    Get facility information for Oakville GO station: elevator, reserved parking,
    wheelchair-accessible trains, ticket sales hours. Call this when the user asks
    about Oakville GO facilities or accessibility.
    """
    if not live_mode.enabled:
        return _DISABLED_MSG
    async with httpx.AsyncClient() as client:
        info = await _get_oakville_facilities(client)

    if not info.get("raw"):
        return "Could not fetch Oakville GO station information — API may be unavailable."

    lines = [
        f"Oakville GO Station:",
        f"  Elevator: {'Available' if info.get('has_elevator') else 'Not listed'}",
        f"  Reserved parking: {'Available' if info.get('has_reserved_parking') else 'Not listed'}",
        f"  Wheelchair-accessible train: {'Yes' if info.get('has_wheelchair_train') else 'Not listed'}",
    ]
    if info.get("ticket_sales_hours"):
        lines.append(f"  Ticket sales: {info['ticket_sales_hours']}")
    if info.get("all_facility_codes"):
        lines.append(f"  All facilities: {', '.join(info['all_facility_codes'])}")
    return "\n".join(lines)


@tool
async def get_next_service(stop_code: str = "OA") -> str:
    """
    Get the next GO train departures from a station.
    Common stop codes: OA (Oakville GO), UN (Union Station), MI (Mississauga GO),
    BR (Brampton GO), CO (Cooksville GO). Call this when the user asks about
    next trains, departure times, or the schedule.
    """
    if not live_mode.enabled:
        return _DISABLED_MSG
    url = GO_API_NEXT_SERVICE_URL.format(stop_code=stop_code)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params={"key": METROLINX_API_KEY}, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        return f"Could not fetch next service for stop {stop_code}: {exc}"

    next_service = data.get("NextService") or {}
    if not next_service:
        meta = data.get("Metadata", {})
        msg = meta.get("ErrorMessage", "No upcoming service found.")
        return f"No upcoming GO service from {stop_code}: {msg}"

    lines = [f"Next GO service from {stop_code}:"]

    for direction in ("Inbound", "Outbound"):
        departures = next_service.get(direction, [])
        if departures:
            lines.append(f"\n{direction}:")
            for dep in departures[:5]:
                route = dep.get("RouteName") or dep.get("RouteCode", "")
                time_str = (
                    dep.get("ScheduledDepartureTime")
                    or dep.get("ScheduledTime")
                    or dep.get("DisplayTime", "")
                )
                status = dep.get("Status", "")
                status_str = f" [{status}]" if status and status.lower() != "on time" else ""
                lines.append(f"  {route} at {time_str}{status_str}")

    if len(lines) == 1:
        lines.append("  No upcoming departures found.")
    return "\n".join(lines)


@tool
async def get_service_exceptions() -> str:
    """
    Get current GO Transit train cancellations, delays, or service exceptions.
    Call this when the user asks about cancellations, service alerts, or disruptions.
    """
    if not live_mode.enabled:
        return _DISABLED_MSG
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                GO_API_EXCEPTIONS_TRAIN_URL,
                params={"key": METROLINX_API_KEY},
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        return f"Could not fetch service exceptions: {exc}"

    # Metrolinx API response shape varies — try multiple keys
    exceptions = (
        data.get("TrainException")
        or data.get("Exceptions")
        or data.get("ServiceException")
        or []
    )
    if not exceptions:
        return "No current GO Transit train service exceptions reported."

    lines = [f"GO Transit service exceptions ({len(exceptions)} found):"]
    for item in exceptions[:10]:
        line_name = item.get("LineName") or item.get("Route") or item.get("Line", "")
        desc = item.get("Description") or item.get("Message") or item.get("Notes", "")
        prefix = f"[{line_name}] " if line_name else ""
        lines.append(f"  {prefix}{desc}")
    return "\n".join(lines)
