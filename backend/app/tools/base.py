from abc import ABC, abstractmethod


class BaseTool(ABC):
    """
    Base class for every Odin tool.
    """

    name = "Base Tool"
    description = "No description"

    @abstractmethod
    def execute(self, *args, **kwargs):
        pass
