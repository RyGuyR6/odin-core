from abc import ABC, abstractmethod


class BasePlugin(ABC):
    name = "Unknown"

    @abstractmethod
    def register(self, container):
        pass
