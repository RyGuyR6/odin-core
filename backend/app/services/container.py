from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from app.core.logger import logger
from app.services.errors import (
    ServiceInitializationError,
    ServiceNotConfiguredError,
    ServiceNotRegisteredError,
)
from app.services.lifecycle import ServiceDefinition, ServiceState, ServiceStatus


class ServiceContainer:
    """Backward-compatible container supporting lazy optional services."""

    def __init__(self):
        self.services: dict[str, Any] = {}
        self._definitions: dict[str, ServiceDefinition] = {}
        self._errors: dict[str, str] = {}
        self._states: dict[str, ServiceState] = {}
        self._lock = threading.RLock()

    def register(self, name: str, service: Any, *, replace: bool = True) -> Any:
        with self._lock:
            if not replace and (name in self.services or name in self._definitions):
                return self.services.get(name)
            self.services[name] = service
            self._definitions.pop(name, None)
            self._errors.pop(name, None)
            self._states[name] = ServiceState.READY
            logger.info(f"Registered service: {name}")
            return service

    def register_factory(
        self,
        name: str,
        factory: Callable[[], Any],
        *,
        required: bool = False,
        configured: Callable[[], bool] | None = None,
        replace: bool = False,
    ) -> None:
        with self._lock:
            if not replace and (name in self.services or name in self._definitions):
                return
            self.services.pop(name, None)
            definition = ServiceDefinition(name, factory, required, configured)
            self._definitions[name] = definition
            self._errors.pop(name, None)
            self._states[name] = (
                ServiceState.REGISTERED
                if definition.is_configured()
                else ServiceState.UNCONFIGURED
            )
            logger.info(f"Registered lazy service: {name}")

    def is_registered(self, name: str) -> bool:
        return name in self.services or name in self._definitions

    def is_initialized(self, name: str) -> bool:
        return name in self.services

    def get(self, name: str, default: Any = None) -> Any:
        with self._lock:
            if name in self.services:
                return self.services[name]

            definition = self._definitions.get(name)
            if definition is None:
                return default

            if not definition.is_configured():
                self._states[name] = ServiceState.UNCONFIGURED
                raise ServiceNotConfiguredError(f"Service '{name}' is not configured.")

            try:
                instance = definition.factory()
            except Exception as exc:
                message = f"{type(exc).__name__}: {exc}"
                self._errors[name] = message
                self._states[name] = ServiceState.ERROR
                raise ServiceInitializationError(
                    f"Service '{name}' failed to initialize: {message}"
                ) from exc

            self.services[name] = instance
            self._errors.pop(name, None)
            self._states[name] = ServiceState.READY
            logger.info(f"Initialized lazy service: {name}")
            return instance

    def require(self, name: str) -> Any:
        if not self.is_registered(name):
            raise ServiceNotRegisteredError(f"Service '{name}' is not registered.")
        service = self.get(name)
        if service is None:
            raise ServiceNotRegisteredError(f"Service '{name}' is not registered.")
        return service

    def reset(self, name: str | None = None) -> None:
        with self._lock:
            if name is None:
                self.services.clear()
                self._errors.clear()
                for service_name, definition in self._definitions.items():
                    self._states[service_name] = (
                        ServiceState.REGISTERED
                        if definition.is_configured()
                        else ServiceState.UNCONFIGURED
                    )
                return

            self.services.pop(name, None)
            self._errors.pop(name, None)
            if name in self._definitions:
                definition = self._definitions[name]
                self._states[name] = (
                    ServiceState.REGISTERED
                    if definition.is_configured()
                    else ServiceState.UNCONFIGURED
                )
            else:
                self._states.pop(name, None)

    def status(self, name: str) -> ServiceStatus:
        if name in self.services:
            definition = self._definitions.get(name)
            return ServiceStatus(
                name=name,
                required=definition.required if definition else True,
                configured=True,
                initialized=True,
                state=self._states.get(name, ServiceState.READY),
                error=self._errors.get(name),
            )

        definition = self._definitions.get(name)
        if definition is None:
            raise ServiceNotRegisteredError(f"Service '{name}' is not registered.")

        configured = definition.is_configured()
        state = self._states.get(
            name,
            ServiceState.REGISTERED if configured else ServiceState.UNCONFIGURED,
        )
        if not configured and state is not ServiceState.ERROR:
            state = ServiceState.UNCONFIGURED

        return ServiceStatus(
            name=name,
            required=definition.required,
            configured=configured,
            initialized=False,
            state=state,
            error=self._errors.get(name),
        )

    def health(self) -> dict[str, dict[str, Any]]:
        names = sorted(set(self.services) | set(self._definitions))
        return {name: self.status(name).as_dict() for name in names}

    def startup(self) -> None:
        """
        Start eager services and required lazy services.

        Successful startup always restores READY, which makes repeated
        FastAPI lifespan/TestClient cycles safe after a prior shutdown.
        """
        for name, service in list(self.services.items()):
            try:
                hook = getattr(service, "startup", None)
                if callable(hook):
                    hook()
                self._errors.pop(name, None)
                self._states[name] = ServiceState.READY
                logger.info(f"Started service: {name}")
            except Exception as exc:
                self._errors[name] = f"{type(exc).__name__}: {exc}"
                self._states[name] = ServiceState.ERROR
                raise

        for name, definition in list(self._definitions.items()):
            if not definition.required or name in self.services:
                continue

            try:
                service = self.require(name)
                hook = getattr(service, "startup", None)
                if callable(hook):
                    hook()
                self._errors.pop(name, None)
                self._states[name] = ServiceState.READY
                logger.info(f"Started required service: {name}")
            except Exception as exc:
                self._errors[name] = f"{type(exc).__name__}: {exc}"
                self._states[name] = ServiceState.ERROR
                raise

    def shutdown(self) -> None:
        for name, service in reversed(list(self.services.items())):
            hook = getattr(service, "shutdown", None)
            if callable(hook):
                hook()
            self._states[name] = ServiceState.STOPPED


container = ServiceContainer()
