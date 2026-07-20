from __future__ import annotations

from app.core.logger import logger
from app.core.settings import settings
from app.services.container import container
from app.services.github import get_github_provider
from app.services.github.client import github_is_configured
from app.services.health_service import HealthService
from app.tools.loader import load_tools
from app.tools.registry import registry


class Odin:
    def __init__(self):
        self.name = settings.APP_NAME
        self.version = settings.VERSION
        self.environment = settings.ENVIRONMENT

        if not container.is_registered("health"):
            container.register("health", HealthService())

        if not container.is_registered("github"):
            container.register_factory(
                "github",
                get_github_provider,
                required=False,
                configured=github_is_configured,
            )

        load_tools()
        logger.info("Odin initialized.")

    def status(self):
        return {
            "name": self.name,
            "version": self.version,
            "environment": self.environment,
            "status": "online",
            "services": container.health(),
            "tools": registry.metadata(),
        }
