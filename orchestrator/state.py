"""
Redis-backed state store for delay tracking (Phase 3).

Each trip is stored as a Redis Hash under key  go:delay:<trip_id>
with fields: last_delay (int seconds), trend (str), updated_at (float epoch).

Keys expire automatically after STATE_TTL_SECONDS — no manual eviction needed.

Public interface is identical to the old in-memory version so processor.py
and any other caller needs no changes.
"""
import time
from typing import Optional

import redis

from config import REDIS_URL

_client: redis.Redis = redis.from_url(REDIS_URL, decode_responses=True)
_PREFIX = "go:delay:"
STATE_TTL_SECONDS = 3600  # matches the old evict_stale default


def _key(trip_id: str) -> str:
    return f"{_PREFIX}{trip_id}"


def get_last_delay(trip_id: str) -> Optional[int]:
    val = _client.hget(_key(trip_id), "last_delay")
    return int(val) if val is not None else None


def update_delay(trip_id: str, current_delay: int) -> dict:
    """
    Record the new delay for trip_id and refresh the key TTL.
    Returns a dict with: trip_id, previous_delay, current_delay, delta, trend.
    """
    previous = get_last_delay(trip_id)
    now = time.time()

    if previous is None:
        trend = "UNKNOWN"
        delta = 0
    else:
        delta = current_delay - previous
        if delta > 30:
            trend = "WORSENING"
        elif delta < -30:
            trend = "RECOVERING"
        else:
            trend = "STABLE"

    pipe = _client.pipeline()
    pipe.hset(_key(trip_id), mapping={
        "last_delay": current_delay,
        "trend": trend,
        "updated_at": now,
    })
    pipe.expire(_key(trip_id), STATE_TTL_SECONDS)
    pipe.execute()

    return {
        "trip_id": trip_id,
        "previous_delay": previous,
        "current_delay": current_delay,
        "delta": delta,
        "trend": trend,
    }


def get_all() -> dict:
    """Return a snapshot of all tracked trips (for debugging / the agent tool)."""
    result = {}
    for key in _client.scan_iter(f"{_PREFIX}*"):
        trip_id = key[len(_PREFIX):]
        entry = _client.hgetall(key)
        if entry:
            result[trip_id] = {
                "last_delay": int(entry["last_delay"]),
                "trend": entry["trend"],
                "updated_at": float(entry["updated_at"]),
            }
    return result


def evict_stale(max_age_seconds: int = STATE_TTL_SECONDS) -> int:
    """No-op — Redis TTL handles expiration automatically. Returns 0."""
    return 0
