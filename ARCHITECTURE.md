# LiveTrackingTrains — Architecture & Kickoff Notes

## What We're Building

A Python microservice system that monitors GO Transit (Metrolinx) realtime data and proactively alerts commuters about delays — specifically on the **Lakeshore West line** with a focus on **Oakville GO station**.

---

## Architecture

### Phase 1 (complete) — Backend pipeline
```
GTFS-RT Protobuf Feeds (Metrolinx)
         ↓
  [1] Ingestor        — polls feeds every 30s, parses Protobuf + JSON
         ↓
  [2] Orchestrator    — filters Lakeshore West, computes delay delta + trend
         ↓
  [3] Notifier        — structured log alerts (pluggable channels)
```

### Phase 2 (planned) — LangChain agent + chat UI
```
Browser (chat UI)
         │  POST /chat
         ▼
  [4] FastAPI server  — serves chat UI + /chat endpoint
         │
         ▼
  [5] LangChain ReAct Agent
         ├── Tool: check_lakeshore_west_delays   → Ingestor + Orchestrator
         ├── Tool: get_oakville_facilities        → go_api/client.py
         ├── Tool: get_next_service              → NextService endpoint
         └── Tool: get_service_exceptions        → Exceptions/Train endpoint
         │
         ▼
  [6] LLM (Claude / GPT-4o)  — natural language answer, streamed to browser
```

---

## Pre-requisites

### 1. API Access (Most Critical — Do This First)
- Register for a **Metrolinx Open Data API key** at api.openmetrolinx.com (or their developer portal)
- You'll need two feeds:
  - **GTFS-RT Trip Updates** (delay data): `https://api.openmetrolinx.com/OpenDataAPI/api/V1/Gtfs.proto/feed/tripUpdates`
  - **GTFS-RT Vehicle Positions**: similar URL
  - **GO REST API** (facility/station metadata): `https://api.openmetrolinx.com/OpenDataAPI/api/V1/Stop/Details/{stopCode}`
- Check if the API requires OAuth or just a static API key in the header

### 2. Static GTFS Data (Reference)
- Download the **GTFS static zip** from Metrolinx to get `trips.txt`, `stops.txt`, `routes.txt`
- You'll need this to map `trip_id` → route (Lakeshore West = route code `"01"`) and `stop_id` → station name (Oakville GO)

### 3. Local Infrastructure
- **Redis** (optional but recommended for state): `winget install Redis.Redis` or Docker: `docker run -d -p 6379:6379 redis`
- **Python 3.11+** (asyncio is mature there)

### 4. Python Packages (requirements.txt)
```
gtfs-realtime-bindings
protobuf>=4.0
httpx
redis
structlog
asyncio
python-dotenv
```

---

## Where to Start (Ordered Steps)

1. Get API access and test the raw feed manually:
   ```bash
   curl -H "Authorization: apikey YOUR_KEY" \
     "https://api.openmetrolinx.com/.../tripUpdates" --output feed.pb
   ```
   Then parse with `gtfs-realtime-bindings` to confirm the structure.

2. Scaffold the folder structure (ingestor / orchestrator / notifier modules).

3. Build the ingestor module first (fetch + parse Protobuf).

4. Add state management (Redis or in-memory dict).

5. Add the delay delta logic + notifier stub.

---

## Key Technical Risks

| Risk | Detail |
|------|--------|
| Feed auth format | Metrolinx may use `x-api-key` header or `apiKey` query param — verify before coding |
| Lakeshore West `route_id` | Must look up in the static GTFS `routes.txt` — not hardcoded in realtime feed |
| Oakville `stop_id` | Same — look up in `stops.txt` |
| Protobuf version mismatch | `gtfs-realtime-bindings` 1.x uses protobuf 3, v0.x uses 2 — pin carefully |
| Redis on Windows | Native Redis doesn't have a Windows binary past v3 — use WSL2 or Docker |

---

## Open Questions (Answer Before Starting)

1. Do you have a Metrolinx API key already?
2. Redis or in-memory dict for state?
3. Notifier output target — WhatsApp (like Temple bot), SMS, or just structured logs for now?
