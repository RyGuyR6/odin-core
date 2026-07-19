from abc import ABC, abstractmethod


class Tool(ABC):
    """
    Base class for every Odin tool.
    """

    name: str = ""
    description: str = ""

    @abstractmethod
    def execute(self, **kwargs) -> dict:
        """
        Execute the tool.

        Returns
        -------
        dict
            JSON-serializable result.
        """
        raise NotImplementedError


BaseTool = Tool
