from __future__ import annotations
from dataclasses import dataclass
from .config import ToolSettings
from .exceptions import ToolPermissionError
from .models import ExecutionContext, PermissionLevel, RiskLevel, ToolDefinition

@dataclass(slots=True)
class PolicyDecision:
    allowed: bool
    requires_approval: bool
    reason: str

class PolicyEngine:
    def __init__(self, settings: ToolSettings):
        self.settings = settings

    def evaluate(self, definition: ToolDefinition, context: ExecutionContext) -> PolicyDecision:
        wildcard = "tools.execute.*"
        if context.permissions:
            missing = [
                permission
                for permission in definition.required_permissions
                if permission not in context.permissions and wildcard not in context.permissions
            ]
            if missing:
                return PolicyDecision(False, False, f"Missing permission: {missing[0]}")

        if definition.name in {"shell.run", "terminal.execute"} and not self.settings.allow_shell:
            return PolicyDecision(False, False, "Shell execution is disabled")
        if definition.name == "python.run" and not self.settings.allow_python:
            return PolicyDecision(False, False, "Python execution is disabled")
        if definition.permission_level is PermissionLevel.restricted:
            return PolicyDecision(False, True, f"Restricted tool: {definition.name}")

        approval = definition.requires_approval
        if definition.category == "filesystem" and definition.name not in {
            "fs.read",
            "fs.list",
            "fs.search",
            "filesystem.read",
            "filesystem.list",
            "filesystem.search",
            "repository.file_search",
            "repository.symbol_search",
            "repository.documentation_lookup",
            "git.status",
            "git.diff",
            "git.branch",
        }:
            approval = approval or self.settings.require_approval_for_writes
        if definition.name in {"shell.run", "python.run", "terminal.execute"}:
            approval = approval or self.settings.require_approval_for_shell
        if definition.risk in {RiskLevel.high, RiskLevel.critical}:
            approval = True
        return PolicyDecision(True, approval, "allowed")

    def require_allowed(self, definition: ToolDefinition, context: ExecutionContext) -> PolicyDecision:
        decision = self.evaluate(definition, context)
        if not decision.allowed:
            raise ToolPermissionError(decision.reason)
        return decision
