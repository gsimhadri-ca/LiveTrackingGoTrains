"""
GO Transit REST API client — station / facility metadata.

Provides:
  - get_stop_details(stop_code)  → raw dict from Metrolinx API
  - get_oakville_facilities()    → convenience wrapper for Oakville GO

API reference: https://api.openmetrolinx.com/OpenDataAPI/Help
Auth: x-api-key header (same key as GTFS-RT feeds)
"""
import structlog
import httpx
from typing import Optional

from config import METROLINX_API_KEY, GO_API_STOP_DETAILS_URL, OAKVILLE_GO_STOP_CODE

log = structlog.get_logger(__name__)

_AUTH_PARAMS = {"key": METROLINX_API_KEY}


async def get_stop_details(client: httpx.AsyncClient, stop_code: str) -> Optional[dict]:
    """
    Fetch facility/status details for a GO station by stop code.
    Returns the parsed JSON dict, or None on error.
    """
    url = GO_API_STOP_DETAILS_URL.format(stop_code=stop_code)
    try:
        response = await client.get(url, params=_AUTH_PARAMS, timeout=10.0)
        response.raise_for_status()
        data = response.json()
        log.debug("stop_details_fetched", stop_code=stop_code, url=url)
        return data
    except httpx.HTTPStatusError as exc:
        log.error("stop_details_http_error", stop_code=stop_code, status=exc.response.status_code)
    except Exception as exc:
        log.error("stop_details_failed", stop_code=stop_code, error=str(exc))
    return None


async def get_oakville_facilities(client: httpx.AsyncClient) -> dict:
    """
    Fetch Oakville GO station details and return a summarized facility snapshot.

    Returns a dict with keys:
      - stop_code
      - elevators: list of {name, status}
      - parking_availability: str or None
      - raw: full API response (for debugging)
    """
    data = await get_stop_details(client, OAKVILLE_GO_STOP_CODE)
    if data is None:
        return {"stop_code": OAKVILLE_GO_STOP_CODE, "elevators": [], "parking_availability": None, "raw": None}

    stop = data.get("Stop", {})

    # Facilities are static metadata — a flat list of {Code, Description}.
    # Metrolinx does not expose real-time elevator status or parking fill % via this API.
    facilities_raw: list = stop.get("Facilities", [])
    facility_codes = {f["Code"]: f["Description"] for f in facilities_raw}

    summary = {
        "stop_code": OAKVILLE_GO_STOP_CODE,
        "stop_name": stop.get("StopName", "Oakville GO"),
        "has_elevator": "EV" in facility_codes,
        "has_reserved_parking": "RP" in facility_codes,
        "has_wheelchair_train": "WAT" in facility_codes,
        "ticket_sales_hours": stop.get("TicketSales"),
        "all_facility_codes": list(facility_codes.keys()),
        # Note: real-time elevator status / parking fill % not available in this API
        "raw": data,
    }

    log.info(
        "oakville_facilities",
        stop_name=summary["stop_name"],
        has_elevator=summary["has_elevator"],
        has_reserved_parking=summary["has_reserved_parking"],
        facilities=summary["all_facility_codes"],
    )
    return summary
