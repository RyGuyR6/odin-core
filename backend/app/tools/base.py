from abc import ABC, abstractmethod


class Tool(ABC):
    """
    Base class for every Odin tool.
    """

    name: str = ""
    description: str = ""
    category: str = "general"
    version: str = "1.0.0"
    tags: list[str] = []

    @abstractmethod
    def execute(self, **kwargs) -> dict:
        raise NotImplementedError

    def metadata(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "version": self.version,
            "tags": self.tags,
        }


BaseTool = Tool
