from app.ai.providers.mock import MockProvider


class AIManager:

    def __init__(self):
        self.provider = MockProvider()

    def ask(self, prompt: str):
        return self.provider.generate(prompt)
