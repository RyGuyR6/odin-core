"""Event models used throughout Odin."""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    """Return the current UTC time in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Event:
    """An immutable event emitted by Odin."""

    type: str
    source: str

    payload: dict[str, Any] = field(default_factory=dict)

    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=utc_now)

    correlation_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable event representation."""
        return asdict(self)
