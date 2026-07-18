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
