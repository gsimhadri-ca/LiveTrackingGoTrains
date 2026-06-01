# LiveTrackingGoTrains — Implementation Progress

**Last updated:** 2026-05-31  
**Status:** Phase 1 complete. Phase 2 in planning — LangChain agent + chat UI.

---

## What Is Built

### Folder Structure

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
├── config.py              # Central config — all env vars loaded here
├── main.py                # Entry point — async poll loop (Ctrl+C to stop)
├── show_delays.py         # One-shot CLI snapshot: all LW trains sorted by delay
├── test_feeds.py          # Integration test — validates all components against live API
├── requirements.txt       # Python dependencies
├── .env                   # Your API key + settings (gitignored)
├── .env.example           # Template for .env
├── .gitignore
└── venv/                  # Isolated Python virtual environment
```

---

## How to Run

### Start the poll loop
```bash
cd D:\Workspace\python_ws\LiveTrackingGoTrains
venv\Scripts\python main.py
```
Polls every 30 seconds. Press `Ctrl+C` to stop.

### Run the integration test (one-shot, no loop)
```bash
venv\Scripts\python test_feeds.py
```

---

## Configuration (`.env`)

| Variable | Default | Description |
|---|---|---|
| `METROLINX_API_KEY` | *(required)* | Your Metrolinx Open Data API key |
| `POLL_INTERVAL_SECONDS` | `30` | How often to poll the feeds |
| `DELAY_THRESHOLD_SECONDS` | `300` | Alert fires when delay ≥ this value AND worsening |
| `LOG_LEVEL` | `INFO` | `DEBUG` shows per-trip delay updates every cycle |

---

## API Endpoints Used

All base URLs: `https://api.openmetrolinx.com/OpenDataAPI/api/V1`  
Auth: `?key=YOUR_API_KEY` query parameter on every request.

| Endpoint | Format | Purpose |
|---|---|---|
| `GET /Gtfs.proto/feed/tripUpdates` | Protobuf binary | Real-time trip delays for all GO lines |
| `GET /Gtfs/Feed/VehiclePosition` | JSON | Real-time vehicle GPS positions |
| `GET /Stop/Details/{StopCode}` | JSON | Station metadata (facilities, hours) |
| `GET /Stop/NextService/{StopCode}` | JSON | Next departures from a station *(not yet wired)* |
| `GET /ServiceUpdate/Exceptions/Train` | JSON | Train cancellations / exceptions *(not yet wired)* |

### Key values discovered from live data (not in docs)
| Fact | Value |
|---|---|
| Lakeshore West `route_id` suffix | `-LW` (full format: `YYYYMMDD-LW`, date prefix rotates daily) |
| Oakville GO `stop_id` in GTFS-RT | `OA` |
| Union Station `stop_id` | `UN` |
| Vehicle positions endpoint returns | JSON (not Protobuf — unlike trip updates) |

---

## Data Flow

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
        │     Computes delta vs last poll:
        │       delta > +30s  → WORSENING
        │       delta < -30s  → RECOVERING
        │       otherwise     → STABLE
        │
        └─ if delay ≥ threshold AND trend == WORSENING:
               dispatch_alert() → notifier
        │
        ▼
[notifier/notifier.py]
  - Builds human-readable alert message
  - Dispatches to all enabled channels
  - Currently: structured log (WARNING level)
  - Future: email, WhatsApp, SMS, dashboard
        │
        ▼
[go_api/client.py]  ← called once at startup
  - get_oakville_facilities()
    Returns: has_elevator, has_reserved_parking, has_wheelchair_train,
             ticket_sales_hours, all facility codes
  Note: Metrolinx REST API provides static facility metadata only —
        real-time elevator status / parking fill % are not available.
```

---

## What the Alert Looks Like

When a Lakeshore West train's delay grows past 5 minutes and is still worsening, the log emits:

```
[warning] DELAY_ALERT
  trip_id=20260422-LW-1988
  route_id=01260426-LW
  current_delay=+3m 14s
  delta=+1m 29s
  trend=WORSENING
  message="GO Train 20260422-LW-1988 (Route 01260426-LW) is now +3m 14s late
           and WORSENING (grew by +1m 29s since last poll).
           Expected delay at Oakville GO: +3m 14s."
```

---

## Notifier Architecture (Pluggable)

[notifier/notifier.py](notifier/notifier.py) is designed for easy extension:

```python
# To add a new notification channel:
# 1. Implement a function:
def _my_channel(alert: dict) -> None:
    ...  # alert has: trip_id, route_id, current_delay_human, delta_human, trend, message

# 2. Add it to the list at the bottom of notifier.py:
_ENABLED_CHANNELS = [
    _log_alert,
    _my_channel,   # ← add here
]
```

### Channels planned (not yet implemented)
- **Email (Gmail SMTP)** — simplest next step, needs `ALERT_FROM_EMAIL`, `ALERT_FROM_APP_PASSWORD`, `ALERT_TO_EMAIL` in `.env`
- **WhatsApp** — reuse existing WhatsApp bot infrastructure
- **Dashboard WebSocket** — push to a browser frontend

---

## What Is NOT Yet Built

| Feature | Phase | Notes |
|---|---|---|
| Email / WhatsApp notifier | 2 | Channel hooks are ready — just needs implementation |
| `NextService/OA` integration | 2 | Would show upcoming Oakville departures alongside delay info |
| `ServiceUpdate/Exceptions/Train` | 2 | Would catch full cancellations (delay = 0 but trip cancelled) |
| User registration / subscription | 2 | Login, preferred trains, alert schedule (days/hours) |
| LangChain agent + tools | 2 | Natural language commute assistant — see Phase 2 plan below |
| Chat UI (FastAPI + HTML) | 2 | Browser chat interface backed by the LangChain agent |
| Persistent state (Redis/DB) | 2 | Currently in-memory — state resets on restart |
| Kafka integration | 3 | For high-throughput / multi-user scaling |

---

## Phase 2 Plan — LangChain Agent + Chat UI

### Goal
Replace the CLI-only `show_delays.py` and bare log alerts with a **conversational AI agent** that answers natural language questions about the user's commute using live Metrolinx data.

### Architecture
```
Browser (chat UI)
      │  POST /chat  { message }
      ▼
FastAPI  ──────────────────────────────────────────────
      │
      ▼
LangChain ReAct Agent
  ├── Tool: check_lakeshore_west_delays()   → calls ingestor + filter (live data)
  ├── Tool: get_oakville_facilities()        → calls go_api/client.py
  ├── Tool: get_next_service(stop_code)      → calls NextService endpoint
  └── Tool: get_service_exceptions()         → calls Exceptions/Train endpoint
      │
      ▼
LLM (Claude claude-sonnet-4-6 or GPT-4o)
      │
      ▼
Natural language answer streamed back to browser
```

### What LangChain Concepts This Teaches
| Concept | Where used |
|---|---|
| `@tool` decorator | Wrapping each Metrolinx API call as a callable tool |
| ReAct agent | Agent decides which tools to call based on user question |
| Chat message history | Agent remembers "my usual train is 8:15 Oakville→Union" |
| Prompt templates | System prompt with commuter context + tool descriptions |
| Streaming output | LLM tokens stream to browser as they arrive |
| Output parsers | Structured delay summaries from raw tool results |

### Example interactions
```
User: "Is the 8:15 Oakville train on time?"
Agent: [calls check_lakeshore_west_delays] → "Yes, train 20260531-LW-1234
       is currently on time. Next departure from Oakville GO is at 8:17."

User: "Any delays over 5 minutes?"
Agent: [calls check_lakeshore_west_delays] → "Two trains are significantly
       delayed: LW-1988 (+12m, worsening) and LW-2041 (+7m, recovering)."

User: "Is the elevator working at Oakville?"
Agent: [calls get_oakville_facilities] → "Yes, elevator is operational.
       Reserved parking is available."
```

### Stack additions
```
langchain>=0.3
langchain-anthropic          # or langchain-openai
fastapi
uvicorn
```

### Open questions before starting
1. Which LLM? Claude (Anthropic key) or GPT-4o (OpenAI key)?
2. Chat UI: minimal plain HTML auto-refresh, or something richer?
3. Conversation memory scope: per browser session, or persistent per user?

---

## Dependencies

```
gtfs-realtime-bindings==1.0.0   # Protobuf GTFS-RT message definitions
protobuf>=4.21,<5.0             # Protobuf runtime (pinned to avoid conflicts)
httpx>=0.27                     # Async HTTP client
structlog>=24.1                 # Structured logging
python-dotenv>=1.0              # .env loading
```

Install into the project venv:
```bash
venv\Scripts\pip install -r requirements.txt
```

> **Note:** Uses an isolated `venv/` — do not use the global Python environment,
> as this project requires `protobuf<5.0` which conflicts with other tools (Fyers SDK etc.).
