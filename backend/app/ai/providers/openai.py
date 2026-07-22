from app.ai.provider import AIProvider


class OpenAIProvider(AIProvider):
    """Stub delegating to the centralized OpenAI LLM platform (OIC-012)."""

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> str:
        from app.llm.service import get_llm_service  # noqa: PLC0415
        from app.llm.models import ChatMessage, ChatRequest  # noqa: PLC0415
        import asyncio  # noqa: PLC0415

        messages = []
        if system_prompt:
            messages.append(ChatMessage(role="system", content=system_prompt))
        messages.append(ChatMessage(role="user", content=prompt))
        request = ChatRequest(messages=messages)
        service = get_llm_service()
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        response = loop.run_until_complete(service.chat(request))
        return response.content
