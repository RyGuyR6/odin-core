class WorkflowRegistry:
    """Stores available workflow definitions keyed by name."""

    def __init__(self) -> None:
        self._workflows: dict[str, object] = {}

    def register(self, name: str, workflow: object) -> None:
        """Register or replace a workflow implementation."""
        self._workflows[name] = workflow

    def get(self, name: str) -> object:
        """Resolve a workflow by name."""
        if name not in self._workflows:
            raise KeyError(f"Workflow '{name}' is not registered.")

        return self._workflows[name]

    def list(self) -> list[str]:
        """List registered workflow names in stable order."""
        return sorted(self._workflows.keys())
