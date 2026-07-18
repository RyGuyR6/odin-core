from abc import ABC, abstractmethod


class Plugin(ABC):

    name = "unknown"
    version = "0.1.0"

    def load(self, context):
        pass

    def unload(self):
        pass

    def tools(self):
        return []
