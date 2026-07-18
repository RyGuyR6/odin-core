from abc import ABC, abstractmethod
from typing import Generic, TypeVar

RequestT = TypeVar("RequestT")
ResponseT = TypeVar("ResponseT")


class Workflow(ABC, Generic[RequestT, ResponseT]):
    """
    Base class for all Odin workflows.
    """

    name: str

    @abstractmethod
    async def execute(self, request: RequestT) -> ResponseT:
        """Execute the workflow."""
        raise NotImplementedError