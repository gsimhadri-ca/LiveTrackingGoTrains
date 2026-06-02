# LiveTrackingGoTrains — Implementation Progress

**Last updated:** 2026-06-01  
**Status:** Phase 3 in progress — Redis, Kafka, subscriptions done. Agent disabled (`AGENT_ENABLED=false`). Set `AGENT_ENABLED=true` to re-enable Claude chat.

---

## Repository

| Branch | Purpose |
|---|---|
| `main` | Active development |
| `production` | Stable / deployable snapshot |

**GitHub:** https://github.com/gsimhadri-ca/LiveTrackingGoTrains

---

## Folder Structure

```
LiveTrackingGoTrains/
├── ingestor/
│   ├── models.py          # Dataclasses: TripUpdate, VehiclePosition, StopTimeUpdate
│   └── fetcher.py         # Async HTTP polling + Protobuf/JSON parsing
├── orchestrator/
│   ├── filter.py          # Lakeshore West + Oakville GO filtering logic
│   ├── state.py           # In-memory delay state store + delta computation
│   └── processor.py       # Main cycle: ingest → filter → delta → alert
├── notifier/
│   └── notifier.py        # Alert dispatcher (structured log output; pluggable channels)
├── go_api/
│   └── client.py          # GO Transit REST API client (station/facility metadata)
├── agent/                 # ← Phase 2
│   ├── tools.py           # 4 async LangChain @tool functions wrapping Metrolinx APIs
│   └── agent.py           # LangGraph create_agent + JSON file history per session
├── static/
│   └── index.html         # Chat UI — GO green theme, suggestion chips, SSE streaming
├── data/                  # Gitignored session history files (history_{id}.json)
├── config.py              # Central config — all env vars loaded here
├── main.py                # Phase 1 entry point — async poll loop (Ctrl+C to stop)
├── server.py              # Phase 2 entry point — FastAPI chat server
├── show_delays.py         # One-shot CLI snapshot: all LW trains sorted by delay
├── test_feeds.py          # Integration test — validates all components against live API
├── requirements.txt       # Python dependencies
├── .env                   # Your API keys + settings (gitignored)
├── .env.example           # Template for .env
├── .gitignore
└── venv/                  # Isolated Python virtual environment
```

---

## How to Run

### Phase 1 — poll loop (no LLM needed)
```bash
cd D:\Workspace\python_ws\LiveTrackingGoTrains
venv\Scripts\python main.py
```

### Phase 1 — one-shot delay snapshot
```bash
venv\Scripts\python show_delays.py
```

### Phase 2 — chat server
```bash
# 1. Add ANTHROPIC_API_KEY to .env first
venv\Scripts\python -m uvicorn server:app --reload --host 127.0.0.1 --port 8000
# Then open http://127.0.0.1:8000
```

---

## Configuration (`.env`)

| Variable | Default | Description |
|---|---|---|
| `METROLINX_API_KEY` | *(required)* | Metrolinx Open Data API key |
| `ANTHROPIC_API_KEY` | *(required for Phase 2)* | Anthropic API key (platform.anthropic.com) |
| `AGENT_MODEL` | `claude-sonnet-4-6` | Claude model for the agent |
| `WEB_HOST` | `127.0.0.1` | FastAPI bind host |
| `WEB_PORT` | `8000` | FastAPI bind port |
| `POLL_INTERVAL_SECONDS` | `30` | Phase 1 poll interval |
| `DELAY_THRESHOLD_SECONDS` | `300` | Phase 1 alert threshold (seconds) |
| `LOG_LEVEL` | `INFO` | `DEBUG` shows per-trip delay updates |

---

## API Endpoints Used

All base URLs: `https://api.openmetrolinx.com/OpenDataAPI/api/V1`  
Auth: `?key=YOUR_API_KEY` query parameter on every request.

| Endpoint | Format | Purpose |
|---|---|---|
| `GET /Gtfs.proto/feed/tripUpdates` | Protobuf binary | Real-time trip delays for all GO lines |
| `GET /Gtfs/Feed/VehiclePosition` | JSON | Real-time vehicle GPS positions |
| `GET /Stop/Details/{StopCode}` | JSON | Station metadata (facilities, hours) |
| `GET /Stop/NextService/{StopCode}` | JSON | Next departures from a station |
| `GET /ServiceUpdate/Exceptions/Train` | JSON | Train cancellations / exceptions |

### Key values discovered from live data (not in docs)
| Fact | Value |
|---|---|
| Lakeshore West `route_id` suffix | `-LW` (full format: `YYYYMMDD-LW`, date prefix rotates daily) |
| Oakville GO `stop_id` in GTFS-RT | `OA` |
| Union Station `stop_id` | `UN` |
| Vehicle positions endpoint returns | JSON (not Protobuf — unlike trip updates) |

---

## Phase 2 — LangChain Agent + Chat UI

### Architecture

```
Browser (http://127.0.0.1:8000)
      │  POST /chat  {message, session_id}
      ▼
FastAPI server.py
      │
      ▼  SSE stream — events: {type: "status"|"answer"|"error", text: "..."}
LangGraph Agent (agent/agent.py)
  ├── Tool: check_lakeshore_west_delays()  → ingestor + filter (live GTFS-RT)
  ├── Tool: get_oakville_station_info()    → go_api/client.py
  ├── Tool: get_next_service(stop_code)    → NextService endpoint
  └── Tool: get_service_exceptions()       → Exceptions/Train endpoint
      │
      ▼
Claude (claude-sonnet-4-6)
      │
      ▼
Natural language answer → SSE → browser
```

### Session history
- Stored in `data/history_{session_id}.json` (gitignored)
- Persists across server restarts
- Clear via UI button → `DELETE /history/{session_id}`

### FastAPI routes
| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | Chat UI |
| `POST` | `/chat` | SSE agent stream |
| `GET` | `/health` | Liveness check |
| `GET` | `/config` | Get `live_mode` state |
| `POST` | `/config` | Set `live_mode` state `{"live_mode": true\|false}` |
| `DELETE` | `/history/{id}` | Clear session history |
| `GET` | `/docs` | Auto-generated API docs |

### Live-data toggle (2026-06-01)
The chat UI has a **Live / Off** toggle switch (top-right of session bar).

| Toggle | Behaviour |
|---|---|
| **Live ON** (default) | All 4 tools call Metrolinx APIs for real-time data |
| **Live OFF** | Tools return a "disabled" message instantly; Claude answers from general knowledge only |

**What still works with Live OFF:** chat UI, conversation history, general GO Transit questions from Claude's training.  
**What stops:** real-time delays, next trains, service exceptions, station facilities.  
**Flag lives in-process** (`agent/live_mode.py`) — resets to ON on server restart.

- `agent/live_mode.py` — single `enabled: bool = True` flag imported by all tools
- Each `@tool` checks `live_mode.enabled` at entry before making any API call
- UI syncs with `GET /config` on page load; posts `{"live_mode": ...}` to `POST /config` on toggle

### Known API quirks (2026-06-01)
- `GET /Stop/NextService/{stop_code}` returns `{"NextService": null}` (not `{}`) when no service
  is scheduled (e.g. overnight). `data.get("NextService", {})` returns `None` in this case —
  fixed with `data.get("NextService") or {}` + early return using the `Metadata.ErrorMessage`.

---

## Data Flow (Phase 1)

```
Metrolinx GTFS-RT feeds
        │
        ▼
[ingestor/fetcher.py]
  - fetch_trip_updates()   → parses Protobuf → List[TripUpdate]
  - fetch_vehicle_positions() → parses JSON → List[VehiclePosition]
  Both fetched concurrently via asyncio.gather()
        │
        ▼
[orchestrator/processor.py]  ← called every poll cycle
        │
        ├─ filter_lakeshore_west_trips()   → keeps route_id ending in "-LW"
        ├─ filter_vehicles_on_lakeshore_west()
        │
        ├─ get_representative_delay()      → prefers Oakville stop delay,
        │                                    falls back to first stop with data
        │
        ├─ state.update_delay(trip_id, delay)
        │     delta > +30s  → WORSENING
        │     delta < -30s  → RECOVERING
        │     otherwise     → STABLE
        │
        └─ if delay ≥ threshold AND trend == WORSENING:
               dispatch_alert() → notifier
        │
        ▼
[notifier/notifier.py]
  Structured log (WARNING level) — pluggable channels ready
```

---

## Notifier Architecture (Pluggable)

```python
# To add a new notification channel:
def _my_channel(alert: dict) -> None:
    ...  # alert has: trip_id, route_id, current_delay_human, delta_human, trend, message

_ENABLED_CHANNELS = [
    _log_alert,
    _my_channel,   # ← add here
]
```

---

## What Is NOT Yet Built

| Feature | Phase | Notes |
|---|---|---|
| Email / WhatsApp notifier | 2 | **DONE (2026-06-01)** — `subscriptions/notifier.py`; SMTP if configured, log-only in dev |
| `NextService/OA` wired to Phase 1 alerts | 2 | Tool exists; not yet in alert message |
| Vultr server deployment | 3 | No server configured yet; local only |
| Persistent state (Redis/DB) | 3 | **DONE (2026-06-01)** — Redis-backed `orchestrator/state.py`; keys TTL 1hr; `REDIS_URL` in config |
| Kafka integration | 3 | **DONE (2026-06-01)** — `kafka/producer.py` + `kafka/consumer.py`; topics `go.trips.delays` + `go.alerts`; KRaft via `docker-compose.yml` |

---

## Dependencies

```
# Phase 1
gtfs-realtime-bindings==1.0.0
protobuf>=4.21,<5.0
httpx>=0.27
structlog>=24.1
python-dotenv>=1.0

# Phase 2
langchain>=0.3          # LangGraph-based agent framework
langchain-anthropic>=0.3
langchain-community>=0.3
anthropic>=0.40
fastapi>=0.115
uvicorn[standard]>=0.30

# Phase 3
redis>=5.0
```

> **Note:** Uses an isolated `venv/` — do not use the global Python environment,
> as this project requires `protobuf<5.0` which conflicts with other tools (Fyers SDK etc.).
