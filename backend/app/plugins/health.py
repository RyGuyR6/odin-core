from app.plugins.base import BasePlugin
from app.services.health_service import HealthService


class HealthPlugin(BasePlugin):
    name = "Health"

    def register(self, container):
        container.register("health", HealthService())
