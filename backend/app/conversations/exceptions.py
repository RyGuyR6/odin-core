class ConversationError(Exception):
    """Base error for Odin's conversation subsystem."""


class ConversationNotFoundError(ConversationError):
    pass


class SessionNotFoundError(ConversationError):
    pass


class ConversationDeletedError(ConversationError):
    pass


class ConversationConflictError(ConversationError):
    pass
