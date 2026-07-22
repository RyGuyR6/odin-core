from app.llm.service import get_llm_service
from app.llm.models import CompletionRequest


class AIManager:
    """Thin adapter that delegates to the centralized LLMService (OIC-012).

    The old mock-based AIManager is replaced here.  All AI requests now
    flow through the LLM platform layer so there is a single code path.
    """

    def ask(self, prompt: str) -> str:
        """Synchronous wrapper for simple prompt completion.

        Note: callers that can be made async should use LLMService directly.
        """
        import asyncio  # noqa: PLC0415
        service = get_llm_service()
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        request = CompletionRequest(prompt=prompt)
        response = loop.run_until_complete(service.complete(request))
        return response.content
