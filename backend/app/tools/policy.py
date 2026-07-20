from __future__ import annotations
from dataclasses import dataclass
from .config import ToolSettings
from .exceptions import ToolPermissionError
from .models import ExecutionContext, RiskLevel, ToolDefinition

@dataclass(slots=True)
class PolicyDecision:
    allowed: bool
    requires_approval: bool
    reason: str

class PolicyEngine:
    def __init__(self, settings: ToolSettings):
        self.settings = settings

    def evaluate(self, definition: ToolDefinition, context: ExecutionContext) -> PolicyDecision:
        required_permission = f"tools.execute.{definition.name}"
        wildcard = "tools.execute.*"
        if context.permissions and required_permission not in context.permissions and wildcard not in context.permissions:
            return PolicyDecision(False, False, f"Missing permission: {required_permission}")

        if definition.name == "shell.run" and not self.settings.allow_shell:
            return PolicyDecision(False, False, "Shell execution is disabled")
        if definition.name == "python.run" and not self.settings.allow_python:
            return PolicyDecision(False, False, "Python execution is disabled")

        approval = definition.requires_approval
        if definition.name.startswith("fs.") and definition.name not in {"fs.read", "fs.list", "fs.search"}:
            approval = approval or self.settings.require_approval_for_writes
        if definition.name in {"shell.run", "python.run"}:
            approval = approval or self.settings.require_approval_for_shell
        if definition.risk in {RiskLevel.high, RiskLevel.critical}:
            approval = True
        return PolicyDecision(True, approval, "allowed")

    def require_allowed(self, definition: ToolDefinition, context: ExecutionContext) -> PolicyDecision:
        decision = self.evaluate(definition, context)
        if not decision.allowed:
            raise ToolPermissionError(decision.reason)
        return decision
