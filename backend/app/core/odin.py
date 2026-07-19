from app.core.logger import logger
from app.core.settings import settings

from app.services.container import container
from app.services.health_service import HealthService
from app.services.github_service import GitHubService

from app.tools.loader import load_tools
from app.tools.registry import registry


class Odin:
    def __init__(self):
        self.name = settings.APP_NAME
        self.version = settings.VERSION
        self.environment = settings.ENVIRONMENT

        container.register("health", HealthService())
        container.register("github", GitHubService())

        load_tools()

        logger.info("Odin initialized.")

    def status(self):
        return {
            "name": self.name,
            "version": self.version,
            "environment": self.environment,
            "status": "online",
            "services": list(container.services.keys()),
            "tools": registry.list(),
        }
