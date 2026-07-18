#!/usr/bin/env bash
set -e

echo "==================================="
echo "Installing Odin Memory Engine"
echo "==================================="

mkdir -p backend/data
mkdir -p backend/app/memory

#########################################
# memory store
#########################################

cat > backend/app/memory/store.py <<'PYEOF'
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
PYEOF

#########################################
# memory service
#########################################

cat > backend/app/services/memory_service.py <<'PYEOF'
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
PYEOF

#########################################
# memory api
#########################################

cat > backend/app/api/memory.py <<'PYEOF'
from fastapi import APIRouter
from pydantic import BaseModel

from app.services.memory_service import MemoryService

router = APIRouter(
    prefix="/memory",
    tags=["Memory"],
)

memory = MemoryService()


class Memory(BaseModel):
    title: str
    content: str


@router.get("")
def list_memory():
    return memory.list()


@router.post("")
def add_memory(item: Memory):
    memory.add(item.title, item.content)
    return {"status": "saved"}


@router.get("/search")
def search_memory(q: str):
    return memory.search(q)
PYEOF

echo
echo "==================================="
echo "Memory Engine Installed"
echo "==================================="
echo
echo "Next:"
echo "Register the memory router."
