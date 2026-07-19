class AgentError(Exception):
    """Base error for Odin's agent subsystem."""


class AgentNotFoundError(AgentError):
    pass


class AgentRunNotFoundError(AgentError):
    pass


class WorkflowNotFoundError(AgentError):
    pass


class WorkflowRunNotFoundError(AgentError):
    pass


class AgentCancelledError(AgentError):
    pass


class AgentPermissionError(AgentError):
    pass


class InvalidWorkflowError(AgentError):
    pass
