from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from app.conversations.manager import ConversationManager, get_conversation_manager
from app.conversations.models import MessageCreate, ConversationCreate
from app.llm.models import ChatMessage, ChatRequest, StreamChunk
from app.llm.service import LLMService, get_llm_service
from app.services.repository_context import repository_context_service

# Maximum characters from the first user message used to build an auto-title prompt.
_AUTO_TITLE_MESSAGE_MAX_LENGTH = 500
_MEMORY_CONTEXT_MAX_CHARS = 2000
_MEMORY_SNIPPET_MAX_LENGTH = 300

log = logging.getLogger(__name__)


class ChatService:
    """Provider-independent chat service built on OIC-008.

    Wraps the conversation manager (persistence) and LLM service (provider
    abstraction) so callers never touch either directly.
    """

    def __init__(
        self,
        conversation_manager: ConversationManager | None = None,
        llm_service: LLMService | None = None,
    ) -> None:
        self._conversations = conversation_manager or get_conversation_manager()
        self._llm = llm_service or get_llm_service()

    # ------------------------------------------------------------------
    # Conversation helpers
    # ------------------------------------------------------------------

    def create_conversation(
        self, title: str | None = None, user_id: str | None = None
    ) -> dict:
        record = self._conversations.create_conversation(
            ConversationCreate(title=title, user_id=user_id)
        )
        return record.model_dump()

    # ------------------------------------------------------------------
    # Non-streaming reply
    # ------------------------------------------------------------------

    async def send_message(
        self,
        conversation_id: str,
        content: str,
        *,
        repository: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> tuple[dict, dict]:
        """Send a user message and return (user_message, assistant_message).

        Uses the injected LLM service so the provider abstraction is always
        consistent with what ChatService was configured with.
        """
        user_request = MessageCreate(role="user", content=content, generate_reply=False)
        user_msg = self._conversations.add_message(conversation_id, user_request)

        conversation = self._conversations.get_conversation(conversation_id)
        messages = self._conversations.list_messages(
            conversation_id,
            limit=max(
                self._conversations.settings.default_history_limit,
                conversation.message_count,
            ),
        )
        context = self._conversations.context_builder.build(
            conversation,
            messages,
            limit=self._conversations.settings.default_context_messages,
        )
        repository_messages = await self._repository_messages(repository, content)
        memory_messages = self._memory_messages(content)

        response = await self._llm.chat(
            ChatRequest(
                messages=[*memory_messages, *repository_messages, *context],
                provider=provider,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                integration_point="native_chat",
                allow_failover=True,
            )
        )
        asst_msg = self._conversations.add_message(
            conversation_id,
            MessageCreate(role="assistant", content=response.content),
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            total_tokens=response.usage.total_tokens,
            provider=response.provider,
            model=response.model,
        )
        return user_msg.model_dump(), asst_msg.model_dump()

    # ------------------------------------------------------------------
    # Streaming reply
    # ------------------------------------------------------------------

    async def stream_reply(
        self,
        conversation_id: str,
        content: str,
        *,
        repository: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Stream the assistant reply, persisting both messages.

        Yields StreamChunk objects.  The user message is saved before the
        first chunk is emitted; the assistant message is saved after the
        stream completes (or on error, partial content is saved).
        """
        user_request = MessageCreate(
            role="user",
            content=content,
            generate_reply=False,
            provider=provider,
            model=model,
        )
        self._conversations.add_message(conversation_id, user_request)

        conversation = self._conversations.get_conversation(conversation_id)
        messages = self._conversations.list_messages(
            conversation_id,
            limit=max(
                self._conversations.settings.default_history_limit,
                conversation.message_count,
            ),
        )
        context = self._conversations.context_builder.build(
            conversation,
            messages,
            limit=self._conversations.settings.default_context_messages,
        )
        repository_messages = await self._repository_messages(repository, content)
        memory_messages = self._memory_messages(content)

        chat_request = ChatRequest(
            messages=[*memory_messages, *repository_messages, *context],
            provider=provider,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            integration_point="native_chat",
            allow_failover=True,
        )

        accumulated = ""
        try:
            async for chunk in self._llm.stream(chat_request):
                accumulated += chunk.delta
                yield chunk
        finally:
            if accumulated:
                self._conversations.add_message(
                    conversation_id,
                    MessageCreate(role="assistant", content=accumulated),
                )

    def _memory_messages(self, query: str) -> list[ChatMessage]:
        """Retrieve relevant memories and format as a system message."""
        try:
            from app.memory import MemoryManager, MemorySearchRequest
            manager = MemoryManager()
            results = manager.search(MemorySearchRequest(
                query=query, mode="hybrid", limit=5, min_score=0.15,
            ))
            if not results:
                return []
            parts = ["Relevant knowledge from memory:"]
            total = 0
            for r in results:
                snippet = r.content[:_MEMORY_SNIPPET_MAX_LENGTH]
                entry = f"- [{r.kind}] {r.title or '(no title)'}: {snippet}"
                if total + len(entry) > _MEMORY_CONTEXT_MAX_CHARS:
                    break
                parts.append(entry)
                total += len(entry)
            if len(parts) > 1:
                return [ChatMessage(role="system", content="\n".join(parts))]
        except Exception:
            log.debug("Memory retrieval skipped in chat", exc_info=True)
        return []

    async def _repository_messages(
        self,
        repository: str | None,
        objective: str,
    ) -> list[ChatMessage]:
        if not repository:
            return []
        package = await repository_context_service.aget_context(repository, objective)
        rendered = repository_context_service.render(package)
        return [ChatMessage(role="system", content=f"Repository context:\n{rendered}")]

    # ------------------------------------------------------------------
    # Auto-title
    # ------------------------------------------------------------------

    async def auto_title(self, conversation_id: str) -> str:
        """Generate and persist a short title from the first user message."""
        messages = self._conversations.list_messages(conversation_id, limit=1)
        if not messages:
            return "New conversation"
        first_content = messages[0].content
        prompt_text = (
            "Summarize the following message as a short 4-6 word chat title. "
            "Reply with only the title, no punctuation at the end.\n\n"
            f"Message: {first_content[:_AUTO_TITLE_MESSAGE_MAX_LENGTH]}"
        )
        from app.llm.models import ChatMessage

        response = await self._llm.chat(
            ChatRequest(
                messages=[ChatMessage(role="user", content=prompt_text)],
                integration_point="native_chat",
                model_role="economy",
            )
        )
        title = response.content.strip().strip('"').strip("'")
        if title:
            from app.conversations.models import ConversationUpdate

            self._conversations.update_conversation(
                conversation_id, ConversationUpdate(title=title)
            )
        return title


_service: ChatService | None = None


def get_chat_service() -> ChatService:
    global _service
    if _service is None:
        _service = ChatService()
    return _service
