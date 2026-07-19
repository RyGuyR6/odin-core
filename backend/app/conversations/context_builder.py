from __future__ import annotations

from app.llm.models import ChatMessage
from .models import ConversationRecord, MessageRecord


class ConversationContextBuilder:
    def build(
        self,
        conversation: ConversationRecord,
        messages: list[MessageRecord],
        *,
        limit: int = 20,
    ) -> list[ChatMessage]:
        selected = messages[-max(1, limit):]
        result: list[ChatMessage] = []
        if conversation.summary:
            result.append(ChatMessage(
                role="system",
                content=f"Conversation summary:\n{conversation.summary}",
            ))
        for message in selected:
            result.append(ChatMessage(
                role=message.role,
                content=message.content,
                name=message.name,
                tool_call_id=message.tool_call_id,
            ))
        return result
