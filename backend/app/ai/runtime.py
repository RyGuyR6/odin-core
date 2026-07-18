from .provider import AIProvider


class AIRuntime:

    def __init__(self):
        self.providers: dict[str, AIProvider] = {}

    def register(self, name: str, provider: AIProvider):
        self.providers[name] = provider

    def provider(self, name: str):
        return self.providers[name]
