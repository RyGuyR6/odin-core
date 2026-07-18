from abc import ABC, abstractmethod


class AIProvider(ABC):

    name = "Unknown"

    @abstractmethod
    def generate(self, prompt: str) -> str:
        pass
