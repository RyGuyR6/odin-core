from __future__ import annotations

import asyncio

from app.services.container import ServiceContainer
from app.services.runtime import ApplicationRuntime, RuntimeState


class SyncService:
    def __init__(self):
        self.started = False
        self.stopped = False

    def startup(self):
        self.started = True

    def shutdown(self):
        self.stopped = True


def test_runtime_starts_required_services_and_records_events():
    service = SyncService()
    services = ServiceContainer()
    services.register_factory("required", lambda: service, required=True)
    runtime = ApplicationRuntime(services)

    asyncio.run(runtime.startup(storage_initialize=lambda: None))

    snapshot = runtime.snapshot()
    assert runtime.state is RuntimeState.READY
    assert snapshot["ready"] is True
    assert service.started is True
    assert [event["component"] for event in snapshot["events"]] == [
        "storage",
        "service-container",
    ]

    asyncio.run(runtime.shutdown())
    assert runtime.state is RuntimeState.STOPPED
    assert service.stopped is True


def test_eager_registered_health_service_is_ready():
    service = SyncService()
    services = ServiceContainer()
    services.register("health", service)
    runtime = ApplicationRuntime(services)

    asyncio.run(runtime.startup())

    snapshot = runtime.snapshot()
    health = snapshot["services"]["health"]

    assert service.started is True
    assert health["required"] is True
    assert health["configured"] is True
    assert health["initialized"] is True
    assert ApplicationRuntime._state_value(health["state"]) == "ready"
    assert snapshot["required_service_failures"] == []
    assert snapshot["ready"] is True
    assert runtime.state is RuntimeState.READY


def test_container_can_restart_after_shutdown():
    service = SyncService()
    services = ServiceContainer()
    services.register("health", service)

    runtime_one = ApplicationRuntime(services)
    asyncio.run(runtime_one.startup())
    asyncio.run(runtime_one.shutdown())

    stopped = services.health()["health"]
    assert stopped["state"] == "stopped"

    runtime_two = ApplicationRuntime(services)
    asyncio.run(runtime_two.startup())

    restarted = services.health()["health"]
    assert restarted["state"] == "ready"
    assert restarted["initialized"] is True
    assert runtime_two.state is RuntimeState.READY
    assert runtime_two.snapshot()["required_service_failures"] == []


def test_unconfigured_optional_service_does_not_block_readiness():
    services = ServiceContainer()
    services.register_factory(
        "optional",
        object,
        required=False,
        configured=lambda: False,
    )
    runtime = ApplicationRuntime(services)

    asyncio.run(runtime.startup())

    snapshot = runtime.snapshot()
    assert snapshot["ready"] is True
    assert snapshot["services"]["optional"]["state"] == "unconfigured"


def test_required_startup_failure_marks_runtime_failed():
    services = ServiceContainer()

    def fail():
        raise RuntimeError("boom")

    services.register_factory("required", fail, required=True)
    runtime = ApplicationRuntime(services)

    try:
        asyncio.run(runtime.startup())
    except Exception:
        pass

    snapshot = runtime.snapshot()
    assert runtime.state is RuntimeState.FAILED
    assert snapshot["ready"] is False
    assert "boom" in snapshot["startup_error"]
