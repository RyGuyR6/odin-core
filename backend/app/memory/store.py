import json
from pathlib import Path


DATA = Path("data/memory.json")


class MemoryStore:

    def __init__(self):
        DATA.parent.mkdir(exist_ok=True)

        if not DATA.exists():
            DATA.write_text("[]")

    def load(self):
        return json.loads(DATA.read_text())

    def save(self, memories):
        DATA.write_text(json.dumps(memories, indent=4))

    def add(self, title, content):
        memories = self.load()

        memories.append(
            {
                "title": title,
                "content": content,
            }
        )

        self.save(memories)

    def all(self):
        return self.load()

    def search(self, text):
        text = text.lower()

        return [
            m
            for m in self.load()
            if text in m["title"].lower()
            or text in m["content"].lower()
        ]
