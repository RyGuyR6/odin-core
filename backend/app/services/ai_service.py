from app.ai.manager import AIManager
from app.services.base import BaseService


class AIService(BaseService):

    name = "AI"

    def __init__(self):
        self.manager = AIManager()

    def ask(self, prompt: str):
        return self.manager.ask(prompt)
