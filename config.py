"""
Central configuration — reads from .env via python-dotenv.
All other modules import from here; nothing reads os.environ directly.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── Metrolinx API ─────────────────────────────────────────────────────────────
METROLINX_API_KEY: str = os.environ["METROLINX_API_KEY"]  # raises if missing

_BASE = "https://api.openmetrolinx.com/OpenDataAPI/api/V1"

# Auth: API key is passed as a query parameter (?key=...)
# All URLs are templates — fetcher appends ?key=METROLINX_API_KEY at runtime

# GTFS-RT Protobuf feeds (GO Transit)
# Protobuf binary feeds (smaller, faster to parse than JSON equivalents)
GTFS_TRIP_UPDATES_URL: str = f"{_BASE}/Gtfs.proto/feed/tripUpdates"
GTFS_VEHICLE_POSITIONS_URL: str = f"{_BASE}/Gtfs/Feed/VehiclePosition"   # JSON; proto path 404s
GTFS_ALERTS_URL: str = f"{_BASE}/Gtfs/Feed/Alerts"

# GO REST API — station/facility metadata
GO_API_STOP_DETAILS_URL: str = f"{_BASE}/Stop/Details/{{stop_code}}"
GO_API_NEXT_SERVICE_URL: str = f"{_BASE}/Stop/NextService/{{stop_code}}"
GO_API_EXCEPTIONS_TRAIN_URL: str = f"{_BASE}/ServiceUpdate/Exceptions/Train"
GO_API_SERVICE_GLANCE_TRAINS_URL: str = f"{_BASE}/ServiceataGlance/Trains/All"

# ── Line / Station constants ───────────────────────────────────────────────────
# Lakeshore West route_id suffix — the date prefix rotates daily (e.g. "01260426-LW").
# Filter by suffix "-LW" to handle date changes automatically.
LAKESHORE_WEST_ROUTE_SUFFIX: str = "-LW"

# Oakville GO station stop_id in the GTFS-RT feed (confirmed from live data)
# Note: "UN" is Union Station, "OA" is Oakville GO
OAKVILLE_STOP_ID: str = "OA"
OAKVILLE_GO_STOP_CODE: str = "OA"     # used for the REST facility API

# ── Behaviour ─────────────────────────────────────────────────────────────────
POLL_INTERVAL_SECONDS: int = int(os.getenv("POLL_INTERVAL_SECONDS", "30"))

# Alert fires when delay grows by at least this many seconds since last poll
DELAY_THRESHOLD_SECONDS: int = int(os.getenv("DELAY_THRESHOLD_SECONDS", "300"))

# ── Anthropic / LangChain agent (Phase 2) ─────────────────────────────────────
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
AGENT_MODEL: str = os.getenv("AGENT_MODEL", "claude-sonnet-4-6")

# ── Web server (Phase 2) ───────────────────────────────────────────────────────
WEB_HOST: str = os.getenv("WEB_HOST", "127.0.0.1")
WEB_PORT: int = int(os.getenv("WEB_PORT", "8000"))

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
