from __future__ import annotations

from app.prompts.models import PromptRenderRequest
from app.prompts.engine import get_prompt_engine
from .models import MessageRecord


class ConversationSummarizer:
    async def summarize(self, messages: list[MessageRecord], *, provider: str | None = None, model: str | None = None) -> str:
        content = "\n".join(f"{message.role}: {message.content}" for message in messages)
        result = await get_prompt_engine().render(PromptRenderRequest(
            template="summarize",
            variables={
                "content": content,
                "audience": "Odin conversation context manager",
                "focus": "Decisions, user preferences, unresolved questions, and next actions",
            },
            call_llm=True,
            provider=provider,
            model=model,
        ))
        if not result.llm_response:
            return ""
        return str(result.llm_response.get("content") or "")
