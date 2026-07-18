from app.core.logger import logger


class ServiceContainer:
    def __init__(self):
        self.services = {}

    def register(self, name, service):
        self.services[name] = service
        logger.info(f"Registered service: {name}")

    def get(self, name):
        return self.services.get(name)

    def startup(self):
        for service in self.services.values():
            service.startup()

    def shutdown(self):
        for service in self.services.values():
            service.shutdown()


container = ServiceContainer()
