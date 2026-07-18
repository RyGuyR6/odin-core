from fastapi import APIRouter
from pydantic import BaseModel

from app.services.ai_service import AIService


router = APIRouter(prefix="/ai", tags=["AI"])

service = AIService()


class Prompt(BaseModel):
    prompt: str


@router.post("/ask")
def ask(prompt: Prompt):
    return {
        "response": service.ask(prompt.prompt)
    }
