class PromptError(Exception):
    """Base error for Odin's prompt subsystem."""


class TemplateNotFoundError(PromptError):
    pass


class TemplateValidationError(PromptError):
    def __init__(self, errors: list[str]):
        super().__init__("Prompt template validation failed.")
        self.errors = errors


class MissingVariableError(PromptError):
    def __init__(self, missing: list[str]):
        super().__init__(f"Missing required variables: {', '.join(sorted(missing))}")
        self.missing = missing


class InvalidTemplateNameError(PromptError):
    pass
