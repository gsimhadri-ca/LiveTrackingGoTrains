from uuid import uuid4
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class Subscription(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    email: str
    route_suffix: str = "LW"           # matches route_id suffix, e.g. "LW" → "-LW"
    min_delay_minutes: int = 5          # only notify when delay >= this many minutes
    notify_hours: list[int] = []        # 0-23 list; empty = all hours
    notify_days: list[str] = []         # "Mon".."Sun"; empty = all days
    active: bool = True
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
