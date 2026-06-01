"""
In-memory state store for delay tracking.

Stores the last known delay per trip_id so the processor can compute
the delay delta (is it getting worse or recovering?).

Structure:
  _store[trip_id] = {
      "last_delay": int,       # seconds
      "trend": str,            # "WORSENING" | "RECOVERING" | "STABLE"
      "updated_at": float,     # epoch seconds
  }
"""
import time
from typing import Optional

_store: dict[str, dict] = {}


def get_last_delay(trip_id: str) -> Optional[int]:
    entry = _store.get(trip_id)
    return entry["last_delay"] if entry else None


def update_delay(trip_id: str, current_delay: int) -> dict:
    """
    Record the new delay for trip_id.
    Returns a dict with keys: trip_id, previous_delay, current_delay, delta, trend.
    """
    previous = get_last_delay(trip_id)
    now = time.time()

    if previous is None:
        trend = "UNKNOWN"
        delta = 0
    else:
        delta = current_delay - previous
        if delta > 30:           # >30s worse → worsening
            trend = "WORSENING"
        elif delta < -30:        # >30s better → recovering
            trend = "RECOVERING"
        else:
            trend = "STABLE"

    _store[trip_id] = {
        "last_delay": current_delay,
        "trend": trend,
        "updated_at": now,
    }

    return {
        "trip_id": trip_id,
        "previous_delay": previous,
        "current_delay": current_delay,
        "delta": delta,
        "trend": trend,
    }


def get_all() -> dict:
    """Return a snapshot of the full state (for debugging/dashboard)."""
    return dict(_store)


def evict_stale(max_age_seconds: int = 3600) -> int:
    """Remove entries not updated within max_age_seconds. Returns eviction count."""
    cutoff = time.time() - max_age_seconds
    stale = [k for k, v in _store.items() if v["updated_at"] < cutoff]
    for k in stale:
        del _store[k]
    return len(stale)
