class ToolError(Exception):
    """Base exception for Odin tool execution."""

class ToolNotFoundError(ToolError):
    pass

class ToolValidationError(ToolError):
    pass

class ToolPermissionError(ToolError):
    pass

class ToolApprovalRequired(ToolError):
    def __init__(self, approval_id: str, message: str = "Approval required"):
        self.approval_id = approval_id
        super().__init__(message)

class ToolExecutionError(ToolError):
    pass

class ToolTimeoutError(ToolExecutionError):
    pass

class ToolCancelledError(ToolExecutionError):
    pass

class SandboxViolationError(ToolPermissionError):
    pass
