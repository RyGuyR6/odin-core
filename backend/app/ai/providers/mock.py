from app.ai.providers.base import AIProvider


class MockProvider(AIProvider):

    name = "Mock"

    def generate(self, prompt: str) -> str:
        return f"[MOCK RESPONSE]\\n{prompt}"
