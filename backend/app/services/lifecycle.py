from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable


class ServiceState(str, Enum):
    REGISTERED = "registered"
    UNCONFIGURED = "unconfigured"
    READY = "ready"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass(slots=True)
class ServiceDefinition:
    name: str
    factory: Callable[[], Any]
    required: bool = False
    configured: Callable[[], bool] | None = None

    def is_configured(self) -> bool:
        return True if self.configured is None else bool(self.configured())


@dataclass(slots=True)
class ServiceStatus:
    name: str
    required: bool
    configured: bool
    initialized: bool
    state: ServiceState
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "required": self.required,
            "configured": self.configured,
            "initialized": self.initialized,
            "state": self.state.value,
            "error": self.error,
        }
