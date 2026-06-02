"""
Redis-backed subscription store.

Keys:
  go:sub:{id}   — JSON-encoded Subscription (string value)
  go:subs       — Set of all subscription IDs
"""
from datetime import datetime, timezone
from typing import Optional

import redis

from config import REDIS_URL
from subscriptions.models import Subscription

_client = redis.from_url(REDIS_URL, decode_responses=True)
_PREFIX = "go:sub:"
_INDEX = "go:subs"


def create(sub: Subscription) -> Subscription:
    _client.set(f"{_PREFIX}{sub.id}", sub.model_dump_json())
    _client.sadd(_INDEX, sub.id)
    return sub


def get(sub_id: str) -> Optional[Subscription]:
    data = _client.get(f"{_PREFIX}{sub_id}")
    return Subscription.model_validate_json(data) if data else None


def list_all() -> list[Subscription]:
    ids = _client.smembers(_INDEX)
    subs = []
    for sub_id in ids:
        sub = get(sub_id)
        if sub:
            subs.append(sub)
    return sorted(subs, key=lambda s: s.created_at)


def delete(sub_id: str) -> bool:
    deleted = _client.delete(f"{_PREFIX}{sub_id}")
    _client.srem(_INDEX, sub_id)
    return deleted > 0


def get_matching(route_id: str, current_delay_s: int) -> list[Subscription]:
    """
    Return all active subscriptions that should receive an alert for this event.
    Filters by: route suffix, minimum delay, allowed hours, allowed days.
    """
    now = datetime.now(timezone.utc)
    current_hour = now.hour
    current_day = now.strftime("%a")  # "Mon", "Tue", ...

    results = []
    for sub in list_all():
        if not sub.active:
            continue
        if not route_id.endswith(f"-{sub.route_suffix}"):
            continue
        if current_delay_s < sub.min_delay_minutes * 60:
            continue
        if sub.notify_hours and current_hour not in sub.notify_hours:
            continue
        if sub.notify_days and current_day not in sub.notify_days:
            continue
        results.append(sub)
    return results
