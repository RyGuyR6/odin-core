class LLMError(Exception):
    """Base error for Odin's LLM subsystem."""


class ProviderNotFoundError(LLMError):
    pass


class ProviderConfigurationError(LLMError):
    pass


class ProviderRequestError(LLMError):
    def __init__(self, message: str, *, status_code: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class AllProvidersFailedError(LLMError):
    def __init__(self, errors: dict[str, str]):
        super().__init__("All candidate LLM providers failed.")
        self.errors = errors
