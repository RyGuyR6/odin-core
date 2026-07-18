from app.memory.store import MemoryStore
from app.services.base import BaseService


class MemoryService(BaseService):

    name = "Memory"

    def __init__(self):
        self.store = MemoryStore()

    def add(self, title, content):
        self.store.add(title, content)

    def list(self):
        return self.store.all()

    def search(self, text):
        return self.store.search(text)
