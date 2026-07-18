from abc import ABC


class BaseService(ABC):
    """Base class for all Odin services."""

    name = "Base Service"

    def startup(self):
        pass

    def shutdown(self):
        pass
