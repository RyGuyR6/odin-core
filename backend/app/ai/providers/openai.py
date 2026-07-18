from app.ai.provider import AIProvider


class OpenAIProvider(AIProvider):

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ):
        raise NotImplementedError(
            "OpenAI integration coming next."
        )
