from typing import Any, List


class WorkflowRegistry:
    """
    Registry for Odin workflow instances.
    """

    def __init__(self):
        self._workflows: dict[str, Any] = {}

    def register(self, name: str, workflow: Any) -> None:
        if not name:
            raise ValueError("Workflow name cannot be empty")

        if not callable(getattr(workflow, "run", None)):
            raise TypeError(
                f"Workflow '{name}' must define a callable run method"
            )

        self._workflows[name] = workflow

    def get(self, name: str) -> Any:
        try:
            return self._workflows[name]
        except KeyError as exc:
            available = ", ".join(self.list()) or "none"
            raise KeyError(
                f"Unknown workflow '{name}'. Available workflows: {available}"
            ) from exc

    def list(self) -> list[str]:
        return sorted(self._workflows.keys())

    def all(self) -> List[Any]:
        return list(self._workflows.values())


registry = WorkflowRegistry()
