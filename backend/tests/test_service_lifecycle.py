from __future__ import annotations

import pytest

from app.services.container import ServiceContainer
from app.services.errors import ServiceNotConfiguredError


class ExampleService:
    def __init__(self):
        self.started = False

    def startup(self):
        self.started = True


def test_factory_is_lazy():
    calls = []
    container = ServiceContainer()
    container.register_factory("example", lambda: calls.append(1) or ExampleService())
    assert calls == []
    assert container.is_initialized("example") is False
    assert isinstance(container.require("example"), ExampleService)
    assert calls == [1]


def test_unconfigured_optional_service_is_not_initialized():
    container = ServiceContainer()
    container.register_factory(
        "optional",
        ExampleService,
        required=False,
        configured=lambda: False,
    )
    assert container.status("optional").state.value == "unconfigured"
    with pytest.raises(ServiceNotConfiguredError):
        container.require("optional")


def test_required_services_start_but_optional_remains_lazy():
    required = ExampleService()
    optional = ExampleService()
    container = ServiceContainer()
    container.register_factory("required", lambda: required, required=True)
    container.register_factory("optional", lambda: optional)
    container.startup()
    assert required.started is True
    assert container.is_initialized("required") is True
    assert optional.started is False
