from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.prompts.exceptions import MissingVariableError, PromptError, TemplateNotFoundError
from app.prompts.models import PromptRenderRequest
from app.prompts.engine import get_prompt_engine

router = APIRouter(prefix="/prompts", tags=["prompts"])


class PromptValidationRequest(BaseModel):
    text: str
    name: str = "inline"
    version: int = Field(default=1, ge=1)


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, TemplateNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, MissingVariableError):
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "missing_variables": exc.missing},
        ) from exc
    if isinstance(exc, PromptError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(status_code=500, detail="Unexpected prompt engine error.") from exc


@router.get("")
async def list_prompts():
    return [item.model_dump() for item in get_prompt_engine().registry.list()]


@router.get("/telemetry")
async def prompt_telemetry():
    return get_prompt_engine().telemetry.summary().model_dump()


@router.get("/{reference}")
async def get_prompt(reference: str):
    try:
        return get_prompt_engine().registry.resolve(reference).model_dump()
    except Exception as exc:
        _raise_http(exc)


@router.post("/render")
async def render_prompt(request: PromptRenderRequest):
    try:
        return (await get_prompt_engine().render(request)).model_dump()
    except Exception as exc:
        _raise_http(exc)


@router.post("/validate")
async def validate_prompt(request: PromptValidationRequest):
    return get_prompt_engine().validate_template(
        request.text,
        name=request.name,
        version=request.version,
    ).model_dump()


@router.post("/reload")
async def reload_prompts():
    try:
        count = get_prompt_engine().reload()
        return {"status": "ok", "templates": count}
    except Exception as exc:
        _raise_http(exc)
