from dataclasses import dataclass, field
from time import time
from uuid import uuid4


@dataclass
class Job:
    tool: str
    payload: dict

    id: str = field(default_factory=lambda: str(uuid4()))
    status: str = "queued"

    created: float = field(default_factory=time)
    started: float | None = None
    completed: float | None = None

    result: dict | None = None
    error: str | None = None
