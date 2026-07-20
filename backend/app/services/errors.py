from __future__ import annotations


class ServiceError(RuntimeError):
    """Base exception for Odin service lifecycle failures."""


class ServiceNotRegisteredError(ServiceError, KeyError):
    """Raised when a requested service has not been registered."""


class ServiceNotConfiguredError(ServiceError):
    """Raised when an optional service is used without configuration."""


class ServiceInitializationError(ServiceError):
    """Raised when a lazy service factory fails."""
