from abc import ABC, abstractmethod


class AIProvider(ABC):

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ):
        raise NotImplementedError
